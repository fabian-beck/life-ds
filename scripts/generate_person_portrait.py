#!/usr/bin/env python3
"""Generate stylized portrait images for persons using the OpenAI image API with multi-size WebP optimization."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup
from openai import APIStatusError, OpenAI
from PIL import Image, ImageOps

from utils.text import slugify

# Set UTF-8 encoding for Windows console with unbuffered output
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", line_buffering=True
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", line_buffering=True
    )


# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
STYLES_PATH = DATA_DIR / "person_styles.json"
PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
PORTRAITS_DIR = PUBLIC_DIR / "portraits"
DEFAULT_MASTER_STYLE_PATH = PUBLIC_DIR / "master_style_portrait.png"
REFERENCE_IMAGE_MAX_DIMENSIONS = (1024, 1536)

# Style transfer prompt for consistent artistic treatment
STYLE_TRANSFER_PROMPT = """Apply the artistic style, color treatment, lighting technique, and rendering approach of the first reference image to the second reference image.

PRESERVE FROM SECOND IMAGE:
- Facial likeness and features EXACTLY
- Expression and gaze direction
- Pose and head position
- Composition and framing
- Historical period clothing and styling

TRANSFER FROM FIRST IMAGE:
- Artistic rendering style (painterly, illustrative, photographic, etc.)
- Color palette and color grading
- Lighting approach and contrast
- Background treatment
- Edge treatment and finishing
- Overall aesthetic mood

CRITICAL:
- The person in the output must be recognizably the same person from the second image
- Do NOT change facial features, expression, or likeness
- Do NOT add decorative elements not present in either image
- Maintain clean, professional quality suitable for biographical visualization
"""

MANDATORY_PORTRAIT_FRAMING = """MANDATORY PORTRAIT FRAMING:
- ALWAYS generate a vertical biographical portrait with the person's face dominant
- Use a head-and-shoulders or upper-torso crop, similar in scale to the FIRST IMAGE
- If the SECOND IMAGE is landscape, full-body, seated, or includes a large environment, crop and reframe it as necessary
- It is explicitly permitted and required to cut away legs, furniture, tables, objects, and background from the SECOND IMAGE
- Never shrink the person to preserve the original composition; likeness takes priority over scene preservation
- Keep the complete head, hair, chin, and shoulders comfortably inside the frame
"""


def get_wikimedia_thumbnail_url(
    url: str,
    max_dimensions: Tuple[int, int] = REFERENCE_IMAGE_MAX_DIMENSIONS,
) -> str:
    """
    Request a suitably sized image URL from the Wikimedia Commons API.

    Args:
        url: Wikimedia Commons URL (thumbnail or original)

    Returns:
        A Wikimedia thumbnail URL, or the original URL if lookup is unavailable.
    """
    parsed = urlparse(url)
    if (
        parsed.netloc.lower() != "upload.wikimedia.org"
        or "/wikipedia/commons/" not in parsed.path
    ):
        return url

    path_parts = parsed.path.rstrip("/").split("/")
    filename = path_parts[-2] if "/thumb/" in parsed.path else path_parts[-1]
    filename = unquote(filename)

    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": max_dimensions[0],
                "iiurlheight": max_dimensions[1],
                "titles": f"File:{filename}",
            },
            headers={
                "User-Agent": (
                    "life-ds-portrait-generator/1.0 "
                    "(+https://github.com/fabian-beck/life-ds)"
                )
            },
            timeout=30,
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        for page in pages.values():
            image_info = page.get("imageinfo") or []
            if image_info and image_info[0].get("thumburl"):
                return str(image_info[0]["thumburl"])
    except (requests.RequestException, ValueError, TypeError) as error:
        print(
            f"  Warning: Wikimedia thumbnail lookup failed: {error}",
            file=sys.stderr,
        )

    return url


def _tag_attr(tag: Any, name: str) -> str:
    """
    Read an attribute off a BeautifulSoup tag as a plain string.

    Multi-valued attributes such as ``class`` come back as lists, and a missing
    tag or attribute comes back as ``None``; normalizing here keeps the
    scraping code below working with strings only.

    Args:
        tag: A BeautifulSoup tag, or None
        name: Attribute name to read

    Returns:
        The attribute value as a string, or "" when absent
    """
    value = tag.get(name) if tag is not None else None
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(str(part) for part in value)
    return str(value)


def extract_image_from_page(page_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract the main image URL from a web page (Openverse, Flickr, Wikimedia Commons, etc.).

    Args:
        page_url: URL to a web page containing an image

    Returns:
        Tuple of (image_url, source_page_url) or (None, None) if extraction fails
    """
    try:
        parsed_url = urlparse(page_url)
        domain = parsed_url.netloc.lower()
        image_url: Optional[str] = None

        # Openverse - use API instead of scraping (they block automated requests)
        if "openverse.org" in domain:
            # URL format: https://openverse.org/image/{image_id}?...
            # API endpoint: https://api.openverse.org/v1/images/{image_id}/
            image_id_match = re.search(r"/image/([a-f0-9-]+)", page_url)
            if image_id_match:
                image_id = image_id_match.group(1)
                api_url = f"https://api.openverse.org/v1/images/{image_id}/"

                api_headers = {
                    "User-Agent": "life-ds-portrait-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
                }
                api_response = requests.get(api_url, headers=api_headers, timeout=30)
                api_response.raise_for_status()
                api_data = api_response.json()

                # Get the full-size image URL
                image_url = api_data.get("url") or api_data.get("thumbnail")

                if image_url:
                    return image_url, page_url

            return None, None

        # For other sites, fetch the HTML page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        response = requests.get(page_url, timeout=30, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Architectuul exposes the subject image as data-image-src in the lead
        # section. Prefer this uncropped asset over og:image, which is a social
        # preview crop and can compromise likeness during style transfer.
        if "architectuul.com" in domain:
            lead_image = soup.select_one("section.lead [data-image-src]")
            image_url = _tag_attr(lead_image, "data-image-src") or None

        # Flickr
        if "flickr.com" in domain:
            # Flickr has specific meta tags
            og_image = soup.find("meta", property="og:image")
            image_url = _tag_attr(og_image, "content") or None

            # Alternative: look for the main photo
            if not image_url:
                main_photo = soup.find(
                    "img", {"class": lambda x: bool(x and "main-photo" in x)}
                )
                image_url = _tag_attr(main_photo, "src") or None

        # Wikimedia Commons file pages
        if "commons.wikimedia.org" in domain and "/File:" in page_url:
            # Look for the full-size image link
            fullsize_link = soup.find(
                "a",
                {"class": "internal"},
                href=lambda x: bool(
                    x and "/wikipedia/commons/" in x and "/thumb/" not in x
                ),
            )
            href = _tag_attr(fullsize_link, "href")
            if href:
                if href.startswith("//"):
                    image_url = "https:" + href
                elif href.startswith("/"):
                    image_url = "https://upload.wikimedia.org" + href
                else:
                    image_url = href

        # Generic fallback: try Open Graph image or largest image on page
        if not image_url:
            og_image = soup.find("meta", property="og:image")
            image_url = _tag_attr(og_image, "content") or None
            if not image_url:
                # Find the largest image on the page
                images = soup.find_all("img")
                max_size = 0
                best_img: Optional[str] = None
                for img in images:
                    src = _tag_attr(img, "src")
                    # Skip tiny images, icons, tracking pixels
                    try:
                        width = int(_tag_attr(img, "width") or 0)
                        height = int(_tag_attr(img, "height") or 0)
                    except (ValueError, TypeError):
                        continue
                    size = width * height
                    if size > max_size and size > 10000:  # At least 100x100
                        max_size = size
                        best_img = src

                if best_img:
                    image_url = best_img

        # Make URL absolute if relative
        if image_url:
            if image_url.startswith("//"):
                image_url = "https:" + image_url
            elif image_url.startswith("/"):
                image_url = f"{parsed_url.scheme}://{parsed_url.netloc}{image_url}"

            return image_url, page_url

        return None, None

    except Exception as e:
        print(f"  Warning: Failed to extract image from page: {e}", file=sys.stderr)
        return None, None


def is_direct_image_url(url: str) -> bool:
    """
    Check if a URL points directly to an image file.

    Args:
        url: URL to check

    Returns:
        True if URL appears to be a direct image URL
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check file extension
    image_extensions = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]
    if any(path.endswith(ext) for ext in image_extensions):
        return True

    # Check for image hosting domains with direct links
    if "staticflickr.com" in parsed.netloc or "upload.wikimedia.org" in parsed.netloc:
        return True

    return False


def download_image(url: str, output_path: Path, max_retries: int = 3) -> bool:
    """
    Download image from URL to local file with retry logic.

    Args:
        url: URL to download from
        output_path: Local path to save to
        max_retries: Number of retry attempts (default: 3)

    Returns:
        True if successful, False otherwise
    """
    thumbnail_url = get_wikimedia_thumbnail_url(url)
    if thumbnail_url != url:
        print(f"  Using Wikimedia thumbnail: {thumbnail_url}")
        url = thumbnail_url

    # Set User-Agent header for Wikimedia Commons compatibility
    headers = {
        "User-Agent": "life-ds-portrait-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30, stream=True, headers=headers)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type and not content_type.lower().startswith("image/"):
                raise requests.RequestException(
                    f"Expected an image response, received {content_type}"
                )

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # A successful HTTP response can still be an HTML error or placeholder.
            # Decode it before allowing the file into the style-transfer request.
            try:
                with Image.open(output_path) as downloaded:
                    downloaded.verify()
            except Exception as error:
                output_path.unlink(missing_ok=True)
                raise requests.RequestException(
                    f"Downloaded response is not a decodable image: {error}"
                ) from error

            return True

        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                print(
                    f"  Download failed (attempt {attempt + 1}/{max_retries}): {e}",
                    file=sys.stderr,
                )
                print(f"  Retrying in {wait_time}s...", file=sys.stderr)
                time.sleep(wait_time)
            else:
                print(
                    f"✗ Error downloading image after {max_retries} attempts: {e}",
                    file=sys.stderr,
                )
                return False

    return False


def validate_image(image_path: Path) -> bool:
    """
    Validate image meets OpenAI requirements.

    Args:
        image_path: Path to image file

    Returns:
        True if valid, False otherwise
    """
    if not image_path.exists():
        print(f"✗ Error: Image file does not exist: {image_path}", file=sys.stderr)
        return False

    # Check file size (<50MB limit)
    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    if file_size_mb > 50:
        print(
            f"✗ Error: Image too large ({file_size_mb:.1f}MB). Maximum size: 50MB",
            file=sys.stderr,
        )
        return False

    # Check format using file extension
    ext = image_path.suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        print(
            f"✗ Error: Unsupported format: {ext}. Supported: .png, .jpg, .jpeg, .webp",
            file=sys.stderr,
        )
        return False

    return True


def prepare_reference_image(
    source_path: Path,
    output_path: Path,
    max_dimensions: Tuple[int, int] = REFERENCE_IMAGE_MAX_DIMENSIONS,
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Create an RGBA PNG reference capped at the generated portrait dimensions."""
    with Image.open(source_path) as source:
        original_size = source.size
        prepared = ImageOps.exif_transpose(source)
        prepared.thumbnail(
            max_dimensions,
            Image.Resampling.LANCZOS,
            reducing_gap=3.0,
        )
        if prepared.mode != "RGBA":
            prepared = prepared.convert("RGBA")

        prepared.save(output_path, "PNG", optimize=True)
        prepared_size = prepared.size

    return original_size, prepared_size


def load_person_registry() -> Dict[str, Any]:
    """Load the persons registry."""
    if not REGISTER_PATH.exists():
        raise FileNotFoundError(f"Persons registry not found: {REGISTER_PATH}")

    try:
        return cast(
            Dict[str, Any], json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
        )
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in persons registry: {e}") from e


def save_person_registry(registry: Dict[str, Any]) -> None:
    """Save the persons registry."""
    REGISTER_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_person_in_registry(
    registry: Dict[str, Any], person_id: str
) -> Optional[Dict[str, Any]]:
    """Find a person entry in the registry by ID."""
    people = registry.get("people", [])
    for person in people:
        if person.get("id") == person_id:
            return cast(Optional[Dict[str, Any]], person)
    return None


def load_person_colors(person_id: str) -> Dict[str, str]:
    """
    Load color scheme for a person from person_styles.json.

    Returns:
        Dict with 'primary' and 'secondary' hex colors, or defaults if not found.
    """
    try:
        with open(STYLES_PATH, "r", encoding="utf-8") as f:
            styles_data = json.load(f)
            person_style = styles_data.get("styles", {}).get(person_id, {})
            return {
                "primary": person_style.get("primary", "#5ED0FF"),
                "secondary": person_style.get("secondary", "#9A7BFF"),
            }
    except Exception as e:
        print(f"  Warning: Could not load colors for {person_id}: {e}", file=sys.stderr)
        return {"primary": "#5ED0FF", "secondary": "#9A7BFF"}


def create_webp_sizes(source_image_path: Path, person_id: str) -> Dict[str, str]:
    """
    Create multiple WebP sizes from source image for optimized loading.

    Args:
        source_image_path: Path to source PNG image
        person_id: Person identifier

    Returns:
        Dict with size keys (thumbnail, medium, full) mapped to local paths
    """
    sizes = {
        "thumbnail": 200,  # For landing page grid
        "medium": 400,  # For story overview slide
        "full": 1024,  # For image viewer
    }

    result_paths = {}

    try:
        # Open source image
        img = Image.open(source_image_path)

        for size_key, target_size in sizes.items():
            # Calculate new dimensions maintaining aspect ratio
            aspect_ratio = img.width / img.height
            if aspect_ratio > 1:
                # Landscape
                new_width = target_size
                new_height = int(target_size / aspect_ratio)
            else:
                # Portrait or square
                new_height = target_size
                new_width = int(target_size * aspect_ratio)

            # Resize image with high-quality Lanczos resampling
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Save as WebP
            output_filename = f"{person_id}_{size_key}.webp"
            output_path = PORTRAITS_DIR / output_filename

            # WebP quality: 85 for full, 80 for smaller sizes (excellent quality, good compression)
            quality = 85 if size_key == "full" else 80
            resized.save(
                output_path, "WEBP", quality=quality, method=6
            )  # method=6 = slowest but best compression

            # Store relative path for use in data files
            result_paths[size_key] = f"/portraits/{output_filename}"

            file_size_kb = output_path.stat().st_size / 1024
            print(
                f"  ✓ Created {size_key} ({new_width}x{new_height}): {output_filename} ({file_size_kb:.1f}KB)"
            )

    except Exception as e:
        print(f"  Warning: Failed to create WebP sizes: {e}", file=sys.stderr)
        # Fallback: use original PNG for all sizes
        fallback_path = f"/portraits/{person_id}.png"
        return {
            "thumbnail": fallback_path,
            "medium": fallback_path,
            "full": fallback_path,
        }

    return result_paths


def update_person_registry(
    person_id: str,
    portrait_paths: Dict[str, str],
    original_image_url: str,
    source_page_url: Optional[str] = None,
    source_license: Optional[str] = None,
    source_creator: Optional[str] = None,
) -> None:
    """
    Update data/persons.json with generated portrait.

    Args:
        person_id: Person identifier
        portrait_paths: Dict with 'thumbnail', 'medium', 'full' paths
        original_image_url: Original image URL used for generation
        source_page_url: Optional source page URL for attribution (e.g., Openverse, Flickr page)
    """
    registry = load_person_registry()
    person = find_person_in_registry(registry, person_id)

    if not person:
        print(f"⚠ Warning: Person {person_id} not found in registry", file=sys.stderr)
        return

    # Preserve original portrait data
    original_portrait = person.get("portrait", {})
    original_caption = original_portrait.get(
        "originalCaption"
    ) or original_portrait.get("caption")

    # Determine source URL: use provided source page, or fall back to original source
    if source_page_url:
        source_url = source_page_url
    else:
        source_url = original_portrait.get("source", "https://commons.wikimedia.org/")

    # Update with generated portrait (multi-size WebP)
    person["portrait"] = {
        "image": portrait_paths.get(
            "thumbnail", portrait_paths.get("full")
        ),  # Default to thumbnail for landing page
        "thumbnail": portrait_paths.get("thumbnail"),
        "medium": portrait_paths.get("medium"),
        "full": portrait_paths.get("full"),
        "source": source_url,
        "caption": "Stylized portrait based on a historical source image",
        "creator": "AI generated artwork",
        "originalImage": original_image_url,
        "referenceUsed": True,
    }
    if source_license:
        person["portrait"]["sourceLicense"] = source_license
    if source_creator:
        person["portrait"]["sourceCreator"] = source_creator

    # Preserve a genuine source caption, but never carry a caption describing
    # an older AI portrait forward as if it described the reference photograph.
    if original_caption and not original_caption.lower().startswith(
        ("ai-generated", "stylized portrait")
    ):
        person["portrait"]["originalCaption"] = original_caption

    save_person_registry(registry)
    sync_translated_registries(person_id, person["portrait"])


def sync_translated_registries(
    person_id: str,
    portrait_data: Dict[str, Any],
) -> None:
    """Synchronize non-translatable portrait metadata to language registries."""
    updated = []
    for registry_path in sorted(DATA_DIR.glob("persons_*.json")):
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            person = find_person_in_registry(registry, person_id)
            if not person:
                continue
            person["portrait"] = portrait_data
            registry_path.write_text(
                json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            updated.append(registry_path.name)
        except (OSError, ValueError, TypeError) as error:
            print(
                f"  Warning: Failed to sync {registry_path.name}: {error}",
                file=sys.stderr,
            )
    if updated:
        print(f"  ? Updated translated registries: {', '.join(updated)}")


def update_life_events_portrait(
    person_id: str,
    portrait_data: Dict[str, Any],
) -> None:
    """
    Update life_events.json with generated portrait for main language and translations.

    Args:
        person_id: Person identifier
        portrait_data: Portrait data dict to sync to life_events.json
    """
    people_dir = DATA_DIR / "people" / person_id

    if not people_dir.exists():
        print(f"  Warning: Person directory not found: {people_dir}", file=sys.stderr)
        return

    # Update main life_events.json
    life_events_file = people_dir / "life_events.json"
    if life_events_file.exists():
        try:
            life_events = json.loads(life_events_file.read_text(encoding="utf-8"))

            if not life_events.get("person"):
                life_events["person"] = {}

            life_events["person"]["portrait"] = portrait_data

            life_events_file.write_text(
                json.dumps(life_events, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print("  ✓ Updated life_events.json")
        except Exception as e:
            print(f"  Warning: Failed to update life_events.json: {e}", file=sys.stderr)

    # Update translated life_events.json files
    updated_translations = []
    for lang_dir in people_dir.iterdir():
        if not lang_dir.is_dir():
            continue

        # Skip _cache directory
        if lang_dir.name.startswith("_"):
            continue

        translated_life_events = lang_dir / "life_events.json"
        if translated_life_events.exists():
            try:
                life_events = json.loads(
                    translated_life_events.read_text(encoding="utf-8")
                )

                if not life_events.get("person"):
                    life_events["person"] = {}

                life_events["person"]["portrait"] = portrait_data

                translated_life_events.write_text(
                    json.dumps(life_events, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                updated_translations.append(lang_dir.name)
            except Exception as e:
                print(
                    f"  Warning: Failed to update {lang_dir.name}/life_events.json: {e}",
                    file=sys.stderr,
                )

    if updated_translations:
        print(f"  ✓ Updated translations: {', '.join(updated_translations)}")


def generate_portrait(
    person_id: str,
    reference_image_url: Optional[str] = None,
    *,
    source_page_url: Optional[str] = None,
    source_license: Optional[str] = None,
    source_creator: Optional[str] = None,
    master_style_path: Path = DEFAULT_MASTER_STYLE_PATH,
    model: str = "gpt-image-2",
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Generate stylized portrait using style transfer.

    Args:
        person_id: Person identifier (e.g., "alan_turing")
        reference_image_url: Optional URL to image file for portrait generation.
                           If None, will load from person's registry entry.
        source_page_url: Optional URL to source page for attribution (e.g., Openverse, Flickr page)
        master_style_path: Path to master style reference image
        model: OpenAI model to use (default: gpt-image-2)
        dry_run: If True, skip API calls and file writes
        force: If True, regenerate even if portrait exists

    Returns:
        Dict with 'id', 'local_path', 'success', 'message'
    """
    print(f"[Step 1/7] Checking prerequisites for '{person_id}'...")

    # Load person's color scheme
    colors = load_person_colors(person_id)
    print(
        f"  Primary color: {colors['primary']}, Secondary color: {colors['secondary']}"
    )

    # If reference_image_url is None, load from registry
    if reference_image_url is None:
        registry = load_person_registry()
        person = find_person_in_registry(registry, person_id)

        if not person:
            error_msg = f"Person '{person_id}' not found in registry"
            print(f"✗ Error: {error_msg}", file=sys.stderr)
            return {
                "id": person_id,
                "success": False,
                "message": error_msg,
            }

        # Get reference portrait URL from registry
        portrait = person.get("portrait", {})
        reference_image_url = portrait.get("image")

        # If portrait is a local path (already generated), use the original image URL
        if reference_image_url and reference_image_url.startswith("/portraits/"):
            reference_image_url = portrait.get("originalImage")
            if reference_image_url:
                print("  Using original image from registry (originalImage field)")

        if not reference_image_url:
            error_msg = f"No reference portrait found for '{person_id}'"
            print(f"✗ Error: {error_msg}", file=sys.stderr)
            print(
                "  Run generate_person_events.py first to create portrait metadata",
                file=sys.stderr,
            )
            return {
                "id": person_id,
                "success": False,
                "message": error_msg,
            }

        # Validate URL format
        if not reference_image_url.startswith("http"):
            error_msg = f"Invalid portrait URL: {reference_image_url}"
            print(f"✗ Error: {error_msg}", file=sys.stderr)
            print("  Portrait should be a valid HTTP(S) URL", file=sys.stderr)
            return {
                "id": person_id,
                "success": False,
                "message": error_msg,
            }

        print(f"  Loaded reference portrait from registry: {reference_image_url}")

    # Check if portrait already exists
    output_path = PORTRAITS_DIR / f"{person_id}.png"
    if output_path.exists() and not force:
        print(f"⊘ Portrait already exists: {output_path}")
        print("  Use --force to regenerate")
        return {
            "id": person_id,
            "local_path": str(output_path),
            "success": True,
            "cached": True,
            "message": "Portrait already exists (use --force to regenerate)",
        }

    # Validate master style portrait exists
    if not master_style_path.exists():
        error_msg = f"Master style portrait not found: {master_style_path}"
        print(f"✗ Error: {error_msg}", file=sys.stderr)
        print(
            "  Create a master style portrait first at public/master_style_portrait.png"
        )
        return {
            "id": person_id,
            "success": False,
            "message": error_msg,
        }

    if not validate_image(master_style_path):
        return {
            "id": person_id,
            "success": False,
            "message": f"Invalid master style image: {master_style_path}",
        }

    print(f"  ✓ Master style portrait found: {master_style_path}")

    # Download reference portrait to temp file
    print("[Step 2/7] Downloading reference portrait...")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_ref_path = Path(temp_dir) / f"{person_id}_ref.jpg"
        temp_ref_png = Path(temp_dir) / f"{person_id}_ref.png"

        if dry_run:
            print("  (Dry run: skipping download)")
        else:
            if not download_image(reference_image_url, temp_ref_path):
                return {
                    "id": person_id,
                    "success": False,
                    "message": f"Failed to download reference image: {reference_image_url}",
                }

            print(f"  ✓ Reference portrait downloaded: {temp_ref_path}")

            # Cap full-resolution scans at the generated portrait dimensions,
            # then convert to RGBA PNG for the image-editing endpoint.
            if temp_ref_path.suffix.lower() in [".jpg", ".jpeg"]:
                try:
                    original_size, prepared_size = prepare_reference_image(
                        temp_ref_path,
                        temp_ref_png,
                    )
                    temp_ref_path = temp_ref_png
                    file_size_mb = temp_ref_path.stat().st_size / (1024 * 1024)
                    print(
                        "  ✓ Prepared reference image: "
                        f"{original_size[0]}x{original_size[1]} → "
                        f"{prepared_size[0]}x{prepared_size[1]} "
                        f"({file_size_mb:.2f} MB)"
                    )
                    if not validate_image(temp_ref_path):
                        return {
                            "id": person_id,
                            "success": False,
                            "message": (
                                "Prepared reference image exceeds API requirements"
                            ),
                        }
                except Exception as e:
                    print(f"✗ Error preparing reference image: {e}", file=sys.stderr)
                    return {
                        "id": person_id,
                        "success": False,
                        "message": f"Image preparation failed: {e}",
                    }

        # Call OpenAI API
        print(f"[Step 3/7] Generating stylized portrait via {model}...")

        if dry_run:
            print("  (Dry run: skipping API call)")
            generated_url = "https://example.com/generated.png"
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

            client = OpenAI(api_key=api_key, timeout=180.0)  # 3 minute timeout

            try:
                print(f"  Using model: {model}")
                print(f"  Master style path: {master_style_path}")
                print(f"  Reference path: {temp_ref_path}")

                # Models that support image editing with multiple images
                if model in ["gpt-image-2", "gpt-image-1.5", "gpt-image-1"]:
                    print(
                        "  Model supports multiple images - using dual-image approach"
                    )
                    # Light-drawing portrait prompt with explicit image role specification
                    enhanced_prompt = f"""You are given TWO reference images:
1. FIRST IMAGE: A style reference showing the artistic treatment to apply
2. SECOND IMAGE: The portrait to transform (this is the PRIMARY source)

Your task: Transform the SECOND IMAGE into a light-drawing portrait using the artistic style from the FIRST IMAGE.

CRITICAL - PRESERVE EXACTLY from SECOND IMAGE:
- Facial likeness and all distinctive features
- Expression and gaze direction EXACTLY as shown
- Head pose, tilt, and angle EXACTLY as shown
- Natural shoulder orientation when visible in the portrait crop
- The person must be IMMEDIATELY recognizable as the same individual
- Hair style and clothing silhouette

{MANDATORY_PORTRAIT_FRAMING}

NO FRAME OR BORDER - the portrait must be borderless:
- Do NOT draw any frame, border, oval, vignette, cartouche, medallion, or decorative surround around the subject
- If the SECOND IMAGE is enclosed in an oval or rectangular frame (common in historical engravings and paintings), IGNORE that frame entirely — render only the person against the plain dark background
- The luminous light strokes belong to the person, their clothing, and hair ONLY — never an enclosing outline or edge treatment
- The background must extend uninterrupted to all four edges of the output with no ring, arch, ellipse, or containing shape

ARTISTIC TREATMENT - Apply from FIRST IMAGE:
- Light-drawing / light-painting aesthetic (glowing strokes in darkness)
- BROAD, BOLD STROKES of light - thick, luminous lines as if drawn with moving light source
- Sketchy, expressive quality - not photorealistic
- Visible light trails and streaks showing movement
- Deep black or very dark background (night photography effect)
- Long-exposure photography feel

COLOR PALETTE:
- Base colors: Pure white (#FFFFFF), {colors['primary']}, and {colors['secondary']}
- White should be the dominant color for the main portrait structure
- Use the two accent colors ({colors['primary']} and {colors['secondary']}) creatively for highlights and emphasis
- You may blend and mix these colors for aesthetic effect where appropriate
- Ensure the overall appearance is visually harmonious and aesthetically pleasing
- Strong contrast between bright glowing strokes and pitch-black background
- Light should have slight bloom/glow effect

OUTPUT FORMAT:
- Portrait format with 2:3 aspect ratio (vertical orientation)
- Head-and-shoulders or upper-torso framing; the face must remain the focal point
- The portrait is "sketched" entirely with glowing light strokes against darkness

REMEMBER: The SECOND IMAGE provides identity, likeness, expression, and recognizable features. The FIRST IMAGE provides only the artistic style. Crop and reframe the SECOND IMAGE whenever needed to produce a true portrait. The result must look like the same person, with NO frame, border, or oval surround."""

                    # Pass both images as file objects in a list
                    # Open files and keep references to close them properly
                    print(f"  Opening master style file: {master_style_path.exists()}")
                    print(f"  Opening reference file: {temp_ref_path.exists()}")

                    style_file = open(master_style_path, "rb")
                    ref_file = open(temp_ref_path, "rb")
                    try:
                        print("  Calling OpenAI API with size=1024x1536, n=1")
                        print(f"  Prompt length: {len(enhanced_prompt)} characters")

                        response = client.images.edit(
                            model=model,
                            image=[style_file, ref_file],
                            prompt=enhanced_prompt,
                            size="1024x1536",  # 2:3 portrait format (closest to 3:4)
                            n=1,
                        )

                        print("  API call completed, processing response...")
                        print(f"  Response type: {type(response)}")
                        print(
                            f"  Response has 'data' attribute: {hasattr(response, 'data')}"
                        )
                        if hasattr(response, "data"):
                            # data is Optional; `or []` keeps a debug print from
                            # being the thing that crashes the run.
                            print(f"  Response data length: {len(response.data or [])}")
                    finally:
                        # Ensure files are closed before temp directory cleanup
                        style_file.close()
                        ref_file.close()

                elif model == "dall-e-2":
                    # DALL-E 2 only supports single image
                    enhanced_prompt = """Sketchy portrait drawn by a torch light in the dark, glowing lines.

PRESERVE EXACTLY:
- Facial likeness and features
- Expression and gaze direction
- Head pose
- Historical period clothing and styling

ALWAYS produce a vertical head-and-shoulders or upper-torso portrait. Crop away the source scene, furniture, and lower body as necessary; never shrink the person to preserve the original composition."""

                    with open(temp_ref_path, "rb") as ref_file:
                        response = client.images.edit(
                            model=model,
                            image=ref_file,
                            prompt=enhanced_prompt,
                            size="1024x1024",
                            n=1,
                        )
                else:
                    # Use generate endpoint for DALL-E 3, etc.
                    print(
                        f"  Note: {model} doesn't support image editing, using text generation",
                        file=sys.stderr,
                    )
                    print(
                        "  This may not preserve facial likeness as accurately",
                        file=sys.stderr,
                    )

                    enhanced_prompt = """Sketchy portrait drawn by a torch light in the dark, glowing lines.
Professional and dignified composition, portrait orientation, shoulders visible."""

                    response = client.images.generate(
                        model=model,
                        prompt=enhanced_prompt,
                        size="1024x1024",
                        n=1,
                    )

                # Extract URL or base64 data from response
                generated_url = None
                generated_b64 = None

                print("  Extracting image data from response...")

                # ImagesResponse.data is Optional, and hasattr only says the
                # attribute exists — len(None) would still raise. Truthiness
                # covers both the missing and the empty case.
                response_data = getattr(response, "data", None)
                if response_data:
                    image_data = response_data[0]
                    print(f"  Image data type: {type(image_data)}")
                    print(f"  Image data attributes: {dir(image_data)}")

                    # Check for URL
                    if hasattr(image_data, "url") and image_data.url:
                        generated_url = image_data.url
                        print("  Found URL in response")
                    # Check for base64 data
                    elif hasattr(image_data, "b64_json") and image_data.b64_json:
                        generated_b64 = image_data.b64_json
                        print("  Found base64 data in response")
                    # Check for revised_prompt (means generation succeeded)
                    elif hasattr(image_data, "revised_prompt"):
                        # Debug: print what we got
                        print(
                            "  Warning: Image data has revised_prompt but no url or b64_json",
                            file=sys.stderr,
                        )
                        if hasattr(image_data, "__dict__"):
                            print(
                                f"  Image data dict: {image_data.__dict__}",
                                file=sys.stderr,
                            )
                    else:
                        print(
                            "  Warning: No url, b64_json, or revised_prompt found",
                            file=sys.stderr,
                        )
                else:
                    print(
                        "  Warning: Response has no data or empty data list",
                        file=sys.stderr,
                    )
                    if hasattr(response, "__dict__"):
                        print(f"  Response dict: {response.__dict__}", file=sys.stderr)

                if not generated_url and not generated_b64:
                    raise ValueError("API returned no URL or base64 data")

                print("  ✓ Portrait generated successfully")
                if generated_url:
                    print(
                        f"  Generated URL: {generated_url[:80]}..."
                        if len(generated_url) > 80
                        else f"  Generated URL: {generated_url}"
                    )
                elif generated_b64:
                    print(f"  Generated base64 data: {len(generated_b64)} characters")

            except APIStatusError as error:
                status_code = getattr(error, "status_code", "unknown")
                message = getattr(getattr(error, "response", {}), "text", str(error))

                error_msg = f"OpenAI API error ({status_code})"
                print(f"✗ {error_msg}: {message}", file=sys.stderr)

                return {
                    "id": person_id,
                    "success": False,
                    "message": f"{error_msg}: {message}",
                }

            except Exception as error:
                print(
                    f"✗ Unexpected error during API call: {type(error).__name__}",
                    file=sys.stderr,
                )
                print(f"✗ Error details: {str(error)}", file=sys.stderr)
                import traceback

                traceback.print_exc()

                return {
                    "id": person_id,
                    "success": False,
                    "message": f"Unexpected error: {str(error)}",
                }

        # Download or save generated image
        print("[Step 4/7] Saving generated portrait...")

        if dry_run:
            print("  (Dry run: skipping save)")
        else:
            # Create portraits directory if it doesn't exist
            PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)

            if generated_url:
                # Download from URL
                if not download_image(generated_url, output_path):
                    return {
                        "id": person_id,
                        "success": False,
                        "message": f"Failed to download generated image from {generated_url}",
                    }
            elif generated_b64:
                # Decode and save base64 data
                import base64

                try:
                    image_bytes = base64.b64decode(generated_b64)
                    output_path.write_bytes(image_bytes)
                except Exception as e:
                    return {
                        "id": person_id,
                        "success": False,
                        "message": f"Failed to decode base64 image: {e}",
                    }

            print(f"  ✓ Portrait saved to: {output_path}")

        # Create optimized WebP sizes
        print("[Step 5/7] Creating optimized WebP sizes...")

        if dry_run:
            print("  (Dry run: skipping WebP creation)")
            portrait_paths = {
                "thumbnail": f"/portraits/{person_id}_thumbnail.webp",
                "medium": f"/portraits/{person_id}_medium.webp",
                "full": f"/portraits/{person_id}_full.webp",
            }
        else:
            portrait_paths = create_webp_sizes(output_path, person_id)

        # Update registry and life_events.json
        print("[Step 6/7] Updating persons registry and life events...")

        if dry_run:
            print("  (Dry run: skipping registry update)")
        else:
            # Update persons.json with multi-size paths and source attribution
            update_person_registry(
                person_id,
                portrait_paths,
                reference_image_url,
                source_page_url,
                source_license,
                source_creator,
            )
            print("  ✓ Registry updated with portrait paths")

            # Get the portrait data that was just saved to the registry
            registry = load_person_registry()
            person = find_person_in_registry(registry, person_id)
            if person and person.get("portrait"):
                # Update life_events.json and translations with the same portrait data
                update_life_events_portrait(person_id, person["portrait"])
            else:
                print(
                    "  Warning: Could not retrieve portrait data from registry",
                    file=sys.stderr,
                )

        print("[Step 7/7] Portrait generation complete!")

        return {
            "id": person_id,
            "local_path": str(output_path),
            "success": True,
            "message": "Portrait generated successfully",
        }


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate stylized portrait images using the OpenAI image API."
    )
    parser.add_argument(
        "person_id_or_name",
        help="Person ID (e.g., 'alan_turing') or name (e.g., 'Alan Turing')",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated portrait",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test without API calls or file writes",
    )
    parser.add_argument(
        "--master-style",
        type=Path,
        default=DEFAULT_MASTER_STYLE_PATH,
        help=f"Path to master style portrait (default: {DEFAULT_MASTER_STYLE_PATH})",
    )
    parser.add_argument(
        "--model",
        default="gpt-image-2",
        help="OpenAI model to use (default: gpt-image-2). Models with image editing support: dall-e-2, gpt-image-1, gpt-image-1.5, gpt-image-2",
    )

    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Optional: Reference image URL to use instead of the one from the registry.",
    )
    parser.add_argument(
        "--source-page",
        default=None,
        help="Landing page used for attribution when --url is a direct image.",
    )
    parser.add_argument(
        "--license",
        default=None,
        help="License of the reference portrait, e.g. 'CC BY-SA 4.0'.",
    )
    parser.add_argument(
        "--source-creator",
        default=None,
        help="Creator or credited source of the reference portrait.",
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # Determine person_id
    person_id_or_name = args.person_id_or_name
    if "_" in person_id_or_name or person_id_or_name.islower():
        person_id = person_id_or_name  # Already a slug
    else:
        person_id = slugify(person_id_or_name)  # Convert name to slug

    print(f"Generating portrait for: {person_id}")
    print(f"Model: {args.model}")
    print(f"Master style: {args.master_style}")
    if args.dry_run:
        print("Mode: DRY RUN (no API calls or file writes)")
    if args.force:
        print("Force: Regenerate even if exists")
    print()

    try:
        # Determine reference image URL and source page URL
        reference_url = None
        source_page_url = args.source_page

        # If --url is provided, check if it's a page or direct image
        if args.url:
            print(f"Processing URL: {args.url}")

            # Check if it's a direct image URL or a web page
            if is_direct_image_url(args.url):
                # Direct image URL
                reference_url = args.url
                print("  Detected direct image URL")
            else:
                # Web page - extract image
                print("  Detected web page - extracting main image...")
                extracted_image_url, extracted_source_url = extract_image_from_page(
                    args.url
                )

                if not extracted_image_url:
                    print(
                        f"✗ Error: Could not extract image from page: {args.url}",
                        file=sys.stderr,
                    )
                    print(
                        "  Please provide a direct image URL instead", file=sys.stderr
                    )
                    return 1

                reference_url = extracted_image_url
                source_page_url = extracted_source_url
                print(f"  ✓ Extracted image URL: {reference_url}")
                print(f"  ✓ Source page for attribution: {source_page_url}")

        else:
            # Load registry to get reference portrait URL
            registry = load_person_registry()
            person = find_person_in_registry(registry, person_id)

            if not person:
                print(
                    f"✗ Error: Person '{person_id}' not found in registry",
                    file=sys.stderr,
                )
                print(f"  Registry path: {REGISTER_PATH}", file=sys.stderr)
                return 1

            # Get reference portrait URL
            portrait = person.get("portrait", {})
            reference_url = portrait.get("image")

            # If portrait is a local path (already generated), use the original image URL
            if reference_url and reference_url.startswith("/portraits/"):
                reference_url = portrait.get("originalImage")
                if reference_url:
                    print("Using original image (stored in originalImage field)")

            if not reference_url:
                print(
                    f"✗ Error: No reference portrait found for '{person_id}'",
                    file=sys.stderr,
                )
                print(
                    "  Run generate_person_events.py first to create portrait",
                    file=sys.stderr,
                )
                return 1

            # Validate URL
            if not reference_url.startswith("http"):
                print(
                    f"✗ Error: Invalid portrait URL: {reference_url}", file=sys.stderr
                )
                print("  Portrait should be a valid HTTP(S) URL", file=sys.stderr)
                return 1

            print(f"Reference portrait: {reference_url}")
            print()

        # Generate portrait
        result = generate_portrait(
            person_id=person_id,
            reference_image_url=reference_url,
            source_page_url=source_page_url,
            source_license=args.license,
            source_creator=args.source_creator,
            master_style_path=args.master_style,
            model=args.model,
            dry_run=args.dry_run,
            force=args.force,
        )

        print()
        if result["success"]:
            if result.get("cached"):
                print(f"⊘ {result['message']}")
            else:
                print("✓ Portrait successfully generated!")
                print(f"  Person ID: {result['id']}")
                print(f"  Local path: {result['local_path']}")
                print(f"  View at: /story/{result['id']}")
            return 0
        else:
            print(f"✗ Portrait generation failed: {result['message']}", file=sys.stderr)
            return 1

    except Exception as error:
        print(f"\n✗ Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
