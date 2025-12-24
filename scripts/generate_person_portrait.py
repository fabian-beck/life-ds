#!/usr/bin/env python3
"""Generate stylized portrait images for persons using OpenAI GPT-Image-1.5 API with multi-size WebP optimization."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
from openai import APIStatusError, OpenAI
from PIL import Image

from config import DEFAULT_MODEL

# Set UTF-8 encoding for Windows console with unbuffered output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)


# Constants
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REGISTER_PATH = DATA_DIR / "persons.json"
STYLES_PATH = DATA_DIR / "person_styles.json"
PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
PORTRAITS_DIR = PUBLIC_DIR / "portraits"
DEFAULT_MASTER_STYLE_PATH = PUBLIC_DIR / "master_style_portrait.png"

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


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def normalize_wikimedia_url(url: str) -> str:
    """
    Convert Wikimedia thumbnail URLs to full-size image URLs.

    Wikimedia thumbnail URLs with specific dimensions (e.g., /thumb/.../NNNpx-...)
    often get rate-limited. This function converts them to the original full-size URL.

    Args:
        url: Wikimedia Commons URL (thumbnail or original)

    Returns:
        Full-size image URL without thumbnail parameters
    """
    # Pattern: https://upload.wikimedia.org/wikipedia/commons/thumb/X/XX/Filename.jpg/NNNpx-Filename.jpg
    # Target:  https://upload.wikimedia.org/wikipedia/commons/X/XX/Filename.jpg

    if "/thumb/" in url:
        parts = url.split("/thumb/")
        if len(parts) == 2:
            # Extract the path after /thumb/ up to the last /
            # e.g., "5/57/Henry_II%2C_Holy_Roman_Emperor.jpg/956px-Henry_II%2C_Holy_Roman_Emperor.jpg"
            path_after_thumb = parts[1]
            # Split by / and take all parts except the last one (which has the size prefix)
            path_components = path_after_thumb.split("/")
            if len(path_components) >= 2:
                # Reconstruct: base_url + /wikipedia/commons/ + path components without last one
                original_path = "/".join(path_components[:-1])
                base_url = parts[0].replace("/thumb", "")
                return f"{base_url}/{original_path}"

    # If not a thumbnail URL or pattern doesn't match, return as-is
    return url


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
    # Normalize Wikimedia URLs to avoid thumbnail rate limiting
    normalized_url = normalize_wikimedia_url(url)
    if normalized_url != url:
        print(f"  Normalized thumbnail URL to original: {normalized_url}")
        url = normalized_url

    # Set User-Agent header for Wikimedia Commons compatibility
    headers = {
        "User-Agent": "life-ds-portrait-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
    }

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30, stream=True, headers=headers)
            response.raise_for_status()

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

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
                print(f"✗ Error downloading image after {max_retries} attempts: {e}", file=sys.stderr)
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


def load_person_registry() -> Dict[str, Any]:
    """Load the persons registry."""
    if not REGISTER_PATH.exists():
        raise FileNotFoundError(f"Persons registry not found: {REGISTER_PATH}")

    try:
        return json.loads(REGISTER_PATH.read_text(encoding="utf-8"))
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
            return person
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
        "medium": 400,     # For story overview slide
        "full": 1024,      # For image viewer
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
            resized.save(output_path, "WEBP", quality=quality, method=6)  # method=6 = slowest but best compression

            # Store relative path for use in data files
            result_paths[size_key] = f"/portraits/{output_filename}"

            file_size_kb = output_path.stat().st_size / 1024
            print(f"  ✓ Created {size_key} ({new_width}x{new_height}): {output_filename} ({file_size_kb:.1f}KB)")

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
) -> None:
    """
    Update data/persons.json with generated portrait.

    Args:
        person_id: Person identifier
        portrait_paths: Dict with 'thumbnail', 'medium', 'full' paths
        original_image_url: Original Wikimedia Commons URL
    """
    registry = load_person_registry()
    person = find_person_in_registry(registry, person_id)

    if not person:
        print(f"⚠ Warning: Person {person_id} not found in registry", file=sys.stderr)
        return

    # Preserve original portrait data
    original_portrait = person.get("portrait", {})
    original_source = original_portrait.get("source")
    original_caption = original_portrait.get("caption")

    # Update with generated portrait (multi-size WebP)
    person["portrait"] = {
        "image": portrait_paths.get("thumbnail", portrait_paths.get("full")),  # Default to thumbnail for landing page
        "thumbnail": portrait_paths.get("thumbnail"),
        "medium": portrait_paths.get("medium"),
        "full": portrait_paths.get("full"),
        "source": original_source or "https://commons.wikimedia.org/",
        "caption": "Stylized portrait based on historical photograph",
        "creator": "AI generated artwork",
        "originalImage": original_image_url,
    }

    # Preserve original caption if it exists
    if original_caption:
        person["portrait"]["originalCaption"] = original_caption

    save_person_registry(registry)


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
            print(f"  ✓ Updated life_events.json")
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
                life_events = json.loads(translated_life_events.read_text(encoding="utf-8"))

                if not life_events.get("person"):
                    life_events["person"] = {}

                life_events["person"]["portrait"] = portrait_data

                translated_life_events.write_text(
                    json.dumps(life_events, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                updated_translations.append(lang_dir.name)
            except Exception as e:
                print(f"  Warning: Failed to update {lang_dir.name}/life_events.json: {e}", file=sys.stderr)

    if updated_translations:
        print(f"  ✓ Updated translations: {', '.join(updated_translations)}")


def generate_portrait(
    person_id: str,
    reference_image_url: str,
    *,
    master_style_path: Path = DEFAULT_MASTER_STYLE_PATH,
    model: str = "gpt-image-1.5",
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Generate stylized portrait using style transfer.

    Args:
        person_id: Person identifier (e.g., "alan_turing")
        reference_image_url: URL to Wikimedia Commons portrait
        master_style_path: Path to master style reference image
        model: OpenAI model to use (default: gpt-image-1.5)
        dry_run: If True, skip API calls and file writes
        force: If True, regenerate even if portrait exists

    Returns:
        Dict with 'id', 'local_path', 'success', 'message'
    """
    print(f"[Step 1/6] Checking prerequisites for '{person_id}'...")

    # Load person's color scheme
    colors = load_person_colors(person_id)
    print(f"  Primary color: {colors['primary']}, Secondary color: {colors['secondary']}")

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
        print("  Create a master style portrait first at public/master_style_portrait.png")
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
    print(f"[Step 2/6] Downloading reference portrait from Wikimedia Commons...")
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

            if not validate_image(temp_ref_path):
                return {
                    "id": person_id,
                    "success": False,
                    "message": f"Invalid reference image: {temp_ref_path}",
                }

            print(f"  ✓ Reference portrait downloaded: {temp_ref_path}")

            # Convert to PNG with alpha channel (DALL-E 2 edit endpoint requires RGBA)
            if temp_ref_path.suffix.lower() in [".jpg", ".jpeg"]:
                try:
                    from PIL import Image
                    img = Image.open(temp_ref_path)
                    # Convert to RGBA (required by DALL-E 2 edit endpoint)
                    if img.mode != "RGBA":
                        # Convert to RGBA, adding opaque alpha channel
                        rgba_img = Image.new("RGBA", img.size)
                        if img.mode == "RGB":
                            rgba_img = img.convert("RGBA")
                        else:
                            # Convert any other mode to RGB first, then to RGBA
                            rgb_img = img.convert("RGB")
                            rgba_img = rgb_img.convert("RGBA")
                        img = rgba_img
                    img.save(temp_ref_png, "PNG")
                    temp_ref_path = temp_ref_png
                    print(f"  ✓ Converted to PNG with alpha channel: {temp_ref_path}")
                except ImportError:
                    print("✗ Error: PIL/Pillow is required to convert JPEG to PNG", file=sys.stderr)
                    print("  Install with: pip install Pillow", file=sys.stderr)
                    return {
                        "id": person_id,
                        "success": False,
                        "message": "PIL/Pillow not installed",
                    }
                except Exception as e:
                    print(f"✗ Error converting image to PNG: {e}", file=sys.stderr)
                    return {
                        "id": person_id,
                        "success": False,
                        "message": f"Image conversion failed: {e}",
                    }

        # Call OpenAI API
        print(f"[Step 3/6] Generating stylized portrait via {model}...")

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
                if model in ["gpt-image-1", "gpt-image-1.5"]:
                    print(f"  Model supports multiple images - using dual-image approach")
                    # Light-drawing portrait prompt with explicit image role specification
                    enhanced_prompt = f"""You are given TWO reference images:
1. FIRST IMAGE: A style reference showing the artistic treatment to apply
2. SECOND IMAGE: The portrait to transform (this is the PRIMARY source)

Your task: Transform the SECOND IMAGE into a light-drawing portrait using the artistic style from the FIRST IMAGE.

CRITICAL - PRESERVE EXACTLY from SECOND IMAGE:
- Facial likeness and all distinctive features
- Expression and gaze direction EXACTLY as shown
- Head pose, tilt, and angle EXACTLY as shown
- Body position, shoulder orientation, and posture
- Composition and framing (head size relative to frame)
- The person must be IMMEDIATELY recognizable as the same individual
- Hair style and clothing silhouette

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
- Portrait format with 3:4 aspect ratio (vertical orientation)
- Match the composition scale from SECOND IMAGE
- The portrait is "sketched" entirely with glowing light strokes against darkness

REMEMBER: The SECOND IMAGE provides the pose, likeness, and composition. The FIRST IMAGE provides only the artistic style. The result must look like the person from the SECOND IMAGE rendered in the style of the FIRST IMAGE."""

                    # Pass both images as file objects in a list
                    # Open files and keep references to close them properly
                    print(f"  Opening master style file: {master_style_path.exists()}")
                    print(f"  Opening reference file: {temp_ref_path.exists()}")

                    style_file = open(master_style_path, "rb")
                    ref_file = open(temp_ref_path, "rb")
                    try:
                        print(f"  Calling OpenAI API with size=1024x1536, n=1")
                        print(f"  Prompt length: {len(enhanced_prompt)} characters")

                        response = client.images.edit(
                            model=model,
                            image=[style_file, ref_file],
                            prompt=enhanced_prompt,
                            size="1024x1536",  # 2:3 portrait format (closest to 3:4)
                            n=1,
                        )

                        print(f"  API call completed, processing response...")
                        print(f"  Response type: {type(response)}")
                        print(f"  Response has 'data' attribute: {hasattr(response, 'data')}")
                        if hasattr(response, 'data'):
                            print(f"  Response data length: {len(response.data)}")
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
- Pose and head position
- Composition and framing
- Historical period clothing and styling"""

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
                    print(f"  Note: {model} doesn't support image editing, using text generation", file=sys.stderr)
                    print(f"  This may not preserve facial likeness as accurately", file=sys.stderr)

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

                print(f"  Extracting image data from response...")

                if hasattr(response, 'data') and len(response.data) > 0:
                    image_data = response.data[0]
                    print(f"  Image data type: {type(image_data)}")
                    print(f"  Image data attributes: {dir(image_data)}")

                    # Check for URL
                    if hasattr(image_data, 'url') and image_data.url:
                        generated_url = image_data.url
                        print(f"  Found URL in response")
                    # Check for base64 data
                    elif hasattr(image_data, 'b64_json') and image_data.b64_json:
                        generated_b64 = image_data.b64_json
                        print(f"  Found base64 data in response")
                    # Check for revised_prompt (means generation succeeded)
                    elif hasattr(image_data, 'revised_prompt'):
                        # Debug: print what we got
                        print(f"  Warning: Image data has revised_prompt but no url or b64_json", file=sys.stderr)
                        if hasattr(image_data, '__dict__'):
                            print(f"  Image data dict: {image_data.__dict__}", file=sys.stderr)
                    else:
                        print(f"  Warning: No url, b64_json, or revised_prompt found", file=sys.stderr)
                else:
                    print(f"  Warning: Response has no data or empty data list", file=sys.stderr)
                    if hasattr(response, '__dict__'):
                        print(f"  Response dict: {response.__dict__}", file=sys.stderr)

                if not generated_url and not generated_b64:
                    raise ValueError("API returned no URL or base64 data")

                print(f"  ✓ Portrait generated successfully")
                if generated_url:
                    print(f"  Generated URL: {generated_url[:80]}..." if len(generated_url) > 80 else f"  Generated URL: {generated_url}")
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
                print(f"✗ Unexpected error during API call: {type(error).__name__}", file=sys.stderr)
                print(f"✗ Error details: {str(error)}", file=sys.stderr)
                import traceback
                traceback.print_exc()

                return {
                    "id": person_id,
                    "success": False,
                    "message": f"Unexpected error: {str(error)}",
                }

        # Download or save generated image
        print(f"[Step 4/6] Saving generated portrait...")

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
        print(f"[Step 5/6] Creating optimized WebP sizes...")

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
        print(f"[Step 6/6] Updating persons registry and life events...")

        if dry_run:
            print("  (Dry run: skipping registry update)")
        else:
            # Update persons.json with multi-size paths
            update_person_registry(person_id, portrait_paths, reference_image_url)
            print(f"  ✓ Registry updated with portrait paths")

            # Get the portrait data that was just saved to the registry
            registry = load_person_registry()
            person = find_person_in_registry(registry, person_id)
            if person and person.get("portrait"):
                # Update life_events.json and translations with the same portrait data
                update_life_events_portrait(person_id, person["portrait"])
            else:
                print(f"  Warning: Could not retrieve portrait data from registry", file=sys.stderr)

        print(f"[Step 7/6] Portrait generation complete!")

        return {
            "id": person_id,
            "local_path": str(output_path),
            "success": True,
            "message": "Portrait generated successfully",
        }


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate stylized portrait images using OpenAI GPT-Image-1.5 API."
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
        default="gpt-image-1",
        help="OpenAI model to use (default: gpt-image-1). Models with image editing support: dall-e-2, gpt-image-1, gpt-image-1.5",
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
        # Load registry to get reference portrait URL
        registry = load_person_registry()
        person = find_person_in_registry(registry, person_id)

        if not person:
            print(f"✗ Error: Person '{person_id}' not found in registry", file=sys.stderr)
            print(f"  Registry path: {REGISTER_PATH}", file=sys.stderr)
            return 1

        # Get reference portrait URL
        portrait = person.get("portrait", {})
        reference_url = portrait.get("image")

        # If portrait is a local path (already generated), use the original Wikimedia URL
        if reference_url and reference_url.startswith("/portraits/"):
            reference_url = portrait.get("originalImage")
            if reference_url:
                print(f"Using original Wikimedia portrait (stored in originalImage field)")

        if not reference_url:
            print(f"✗ Error: No reference portrait found for '{person_id}'", file=sys.stderr)
            print("  Run generate_person_events.py first to create portrait", file=sys.stderr)
            return 1

        # Handle Wikimedia Commons URLs
        if not reference_url.startswith("http"):
            print(f"✗ Error: Invalid portrait URL: {reference_url}", file=sys.stderr)
            print("  Portrait should be a Wikimedia Commons URL", file=sys.stderr)
            return 1

        print(f"Reference portrait: {reference_url}")
        print()

        # Generate portrait
        result = generate_portrait(
            person_id=person_id,
            reference_image_url=reference_url,
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
                print(f"✓ Portrait successfully generated!")
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
