#!/usr/bin/env python3
"""Wikipedia materials caching utilities for generation scripts."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import unquote, urlparse

import requests

# Constants from generate_person_dataset.py
MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
MEDIAWIKI_API_DE = "https://de.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
WIKIPEDIA_SUMMARY_API_DE = "https://de.wikipedia.org/api/rest_v1/page/summary/"

# How much longer the German article must be before it is preferred over the
# English one. English is the base language of the datasets, and a few percent
# of extra characters says nothing about which article is better sourced — for
# Benjamin Franklin (+1.8%) and George Washington (+5%) it picked German for
# American founding fathers, which also sends the related-article search after
# German titles. A German article that is genuinely the richer one clears this
# comfortably.
DE_PREFERENCE_MARGIN = 1.2
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
DEFAULT_USER_AGENT = (
    "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PEOPLE_DIR = DATA_DIR / "people"


def slugify(value: str) -> str:
    """Convert a string into a URL-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    return slug.strip("_") or "person"


def wikipedia_headers() -> Dict[str, str]:
    """Return headers for Wikipedia API requests."""
    user_agent = os.getenv("WIKIPEDIA_USER_AGENT", DEFAULT_USER_AGENT)
    return {"User-Agent": user_agent}


def is_url(value: str) -> bool:
    """Report whether a string is an http(s) URL rather than a subject name."""
    value = (value or "").strip()
    return value.startswith("http://") or value.startswith("https://")


def extract_wikipedia_title(url_or_subject: str) -> Optional[Tuple[str, str]]:
    """Extract the article title and language code from a Wikipedia URL.

    Supports URLs like:
    - https://en.wikipedia.org/wiki/Ada_Lovelace
    - https://de.wikipedia.org/wiki/Hanna_Nagel
    - http://en.wikipedia.org/wiki/Antoni_Gaud%C3%AD

    Returns ``(article_title, language_code)`` for a Wikipedia article URL and
    ``None`` for anything else, including a plain subject name.
    """
    url_or_subject = (url_or_subject or "").strip()
    if not is_url(url_or_subject):
        return None

    try:
        parsed = urlparse(url_or_subject)
    except ValueError:
        return None

    if not parsed.netloc or "wikipedia.org" not in parsed.netloc:
        return None

    domain_parts = parsed.netloc.split(".")
    if (
        len(domain_parts) >= 3
        and domain_parts[-2] == "wikipedia"
        and domain_parts[-1] == "org"
        and domain_parts[0] != "www"
    ):
        lang_code = domain_parts[0]
    else:
        lang_code = "en"

    # The path is /wiki/Article_Title; the title itself may contain slashes.
    path_parts = parsed.path.split("/")
    if len(path_parts) < 3 or path_parts[1] != "wiki":
        return None

    title = unquote("/".join(path_parts[2:])).replace("_", " ").strip()
    if not title:
        return None
    return (title, lang_code)


def get_cache_dir(person_id: str) -> Path:
    """Get the cache directory for a person."""
    return PEOPLE_DIR / person_id / "_cache"


def cache_exists(person_id: str) -> bool:
    """Check if cache exists for a person."""
    cache_dir = get_cache_dir(person_id)
    return (
        (cache_dir / "wikipedia_page.json").exists()
        and (cache_dir / "wikipedia_summary.json").exists()
        and (cache_dir / "commons_images.json").exists()
    )


def _strip_html_tags(value: str) -> str:
    """Remove HTML tags from text."""
    # Remove HTML tags
    clean = re.sub(r"<[^>]+>", "", value)
    # Decode HTML entities
    clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    clean = clean.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Remove excessive whitespace
    clean = " ".join(clean.split())
    return clean.strip()


def _fetch_wikipedia_page_from_api(title: str, api_url: str) -> Dict[str, Any]:
    """Fetch Wikipedia page data from a specific API endpoint."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts|pageimages|info|images",
        "explaintext": 1,
        "redirects": 1,
        "inprop": "url",
        "piprop": "original",
        "titles": title,
        "imlimit": 100,  # Fetch up to 100 images from the page
    }
    response = requests.get(
        api_url,
        params=params,
        timeout=30,
        headers=wikipedia_headers(),
    )
    response.raise_for_status()
    data = response.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        raise ValueError(f"No Wikipedia page found for '{title}'.")
    page = next(iter(pages.values()))
    if "missing" in page:
        raise ValueError(f"Wikipedia page for '{title}' is missing.")
    return cast(Dict[str, Any], page)


def _fetch_wikipedia_page_direct(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia page data, preferring German only if decisively longer.

    Falls back to German when no English article exists.
    """
    en_page = None
    de_page = None

    # Try English first
    try:
        en_page = _fetch_wikipedia_page_from_api(title, MEDIAWIKI_API)
    except ValueError:
        pass  # English article doesn't exist

    # Try German
    try:
        de_page = _fetch_wikipedia_page_from_api(title, MEDIAWIKI_API_DE)
    except ValueError:
        pass  # German article doesn't exist

    # If no English article, use German
    if en_page is None and de_page is not None:
        de_page["_source_language"] = "de"
        return de_page

    # If no German article, use English
    if de_page is None and en_page is not None:
        en_page["_source_language"] = "en"
        return en_page

    # If both exist, compare lengths
    if en_page is not None and de_page is not None:
        en_extract = en_page.get("extract", "")
        de_extract = de_page.get("extract", "")

        # Use German only if it is decisively longer (see DE_PREFERENCE_MARGIN).
        if len(de_extract) > len(en_extract) * DE_PREFERENCE_MARGIN:
            de_page["_source_language"] = "de"
            return de_page
        else:
            en_page["_source_language"] = "en"
            return en_page

    # Neither exists
    raise ValueError(f"No Wikipedia page found for '{title}' in English or German.")


def _fetch_wikipedia_summary_from_api(title: str, api_url: str) -> Dict[str, Any]:
    """Fetch Wikipedia summary from a specific API endpoint."""
    from urllib.parse import quote

    url = api_url + quote(title.replace(" ", "_"))
    response = requests.get(url, timeout=30, headers=wikipedia_headers())
    if response.status_code != 200:
        return {}
    return cast(Dict[str, Any], response.json())


def _fetch_wikipedia_summary_direct(title: str) -> Dict[str, Any]:
    """Fetch Wikipedia summary, preferring German only if decisively longer.

    Falls back to German when no English summary exists.
    """
    en_summary = _fetch_wikipedia_summary_from_api(title, WIKIPEDIA_SUMMARY_API)
    de_summary = _fetch_wikipedia_summary_from_api(title, WIKIPEDIA_SUMMARY_API_DE)

    # If no English summary, use German
    if not en_summary and de_summary:
        de_summary["_source_language"] = "de"
        return de_summary

    # If no German summary, use English
    if not de_summary and en_summary:
        en_summary["_source_language"] = "en"
        return en_summary

    # If both exist, compare lengths
    if en_summary and de_summary:
        en_extract = en_summary.get("extract", "")
        de_extract = de_summary.get("extract", "")

        # Use German only if it is decisively longer (see DE_PREFERENCE_MARGIN).
        if len(de_extract) > len(en_extract) * DE_PREFERENCE_MARGIN:
            de_summary["_source_language"] = "de"
            return de_summary
        else:
            en_summary["_source_language"] = "en"
            return en_summary

    return {}


def _fetch_commons_images_direct(
    person_name: str, limit: int = 30
) -> List[Dict[str, Any]]:
    """Fetch Commons images directly from API."""
    try:
        # Search Commons for images related to the person
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{person_name}",
            "srnamespace": "6",  # File namespace
            "srlimit": limit,
            "srprop": "snippet",
        }
        response = requests.get(
            COMMONS_API,
            params=params,
            timeout=30,
            headers=wikipedia_headers(),
        )
        response.raise_for_status()
        data = response.json()

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return []

        # Extract file titles
        file_titles = [
            result.get("title") for result in search_results if result.get("title")
        ]

        # Fetch detailed info for these files
        if not file_titles:
            return []

        image_data = []
        # Process in chunks of 50
        for i in range(0, len(file_titles), 50):
            chunk = file_titles[i : i + 50]
            params = {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "titles": "|".join(chunk),
            }

            try:
                response = requests.get(
                    COMMONS_API,
                    params=params,
                    timeout=30,
                    headers=wikipedia_headers(),
                )
                response.raise_for_status()
                data = response.json()
            except Exception as error:
                print(f"Warning: Failed to fetch Commons image details: {error}")
                continue

            pages = data.get("query", {}).get("pages", {})
            for page in pages.values():
                imageinfo = page.get("imageinfo", [])
                if imageinfo and len(imageinfo) > 0:
                    info = imageinfo[0]
                    url = info.get("url")
                    mime = info.get("mime", "")
                    width = info.get("width", 0)
                    height = info.get("height", 0)

                    # Only include proper images
                    if (
                        url
                        and mime.startswith("image/")
                        and width >= 100
                        and height >= 100
                    ):
                        extmetadata = info.get("extmetadata", {})
                        description = None
                        description_url = None

                        if "ImageDescription" in extmetadata:
                            desc_data = extmetadata["ImageDescription"]
                            if isinstance(desc_data, dict) and "value" in desc_data:
                                description = _strip_html_tags(desc_data["value"])

                        if "DescriptionURL" in extmetadata:
                            desc_url_data = extmetadata["DescriptionURL"]
                            if (
                                isinstance(desc_url_data, dict)
                                and "value" in desc_url_data
                            ):
                                description_url = desc_url_data["value"]
                        elif "descriptionurl" in info:
                            description_url = info["descriptionurl"]

                        image_obj = {
                            "url": url,
                            "caption": description or "Image from Wikimedia Commons",
                            "source": description_url,
                        }
                        image_data.append(image_obj)

        return image_data
    except Exception as error:
        print(f"Warning: Commons search failed for '{person_name}': {error}")
        return []


def save_cache(
    person_id: str,
    page_data: Dict[str, Any],
    summary_data: Dict[str, Any],
    commons_images: List[Dict[str, Any]],
) -> None:
    """Save Wikipedia materials to cache."""
    cache_dir = get_cache_dir(person_id)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Save page data
    (cache_dir / "wikipedia_page.json").write_text(
        json.dumps(page_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Save summary data
    (cache_dir / "wikipedia_summary.json").write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Save Commons images
    (cache_dir / "commons_images.json").write_text(
        json.dumps(commons_images, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_from_cache(
    person_id: str,
) -> tuple[
    Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]
]:
    """Load Wikipedia materials from cache if available."""
    cache_dir = get_cache_dir(person_id)

    page_data = None
    summary_data = None
    commons_images = None

    try:
        if (cache_dir / "wikipedia_page.json").exists():
            page_data = json.loads(
                (cache_dir / "wikipedia_page.json").read_text(encoding="utf-8")
            )
    except json.JSONDecodeError:
        pass

    try:
        if (cache_dir / "wikipedia_summary.json").exists():
            summary_data = json.loads(
                (cache_dir / "wikipedia_summary.json").read_text(encoding="utf-8")
            )
    except json.JSONDecodeError:
        pass

    try:
        if (cache_dir / "commons_images.json").exists():
            commons_images = json.loads(
                (cache_dir / "commons_images.json").read_text(encoding="utf-8")
            )
    except json.JSONDecodeError:
        pass

    return page_data, summary_data, commons_images


def get_cached_wikipedia_page(
    person_id: str, title: str, use_cache: bool = True
) -> Dict[str, Any]:
    """Get Wikipedia page data, using cache if available."""
    if use_cache:
        page_data, _, _ = load_from_cache(person_id)
        if page_data is not None:
            return page_data

    # Fetch from API
    page_data = _fetch_wikipedia_page_direct(title)
    return page_data


def get_cached_wikipedia_summary(
    person_id: str, title: str, use_cache: bool = True
) -> Dict[str, Any]:
    """Get Wikipedia summary, using cache if available."""
    if use_cache:
        _, summary_data, _ = load_from_cache(person_id)
        if summary_data is not None:
            return summary_data

    # Fetch from API
    summary_data = _fetch_wikipedia_summary_direct(title)
    return summary_data


def get_cached_commons_images(
    person_id: str, person_name: str, limit: int = 30, use_cache: bool = True
) -> List[Dict[str, Any]]:
    """Get Commons images, using cache if available."""
    if use_cache:
        _, _, commons_images = load_from_cache(person_id)
        if commons_images is not None:
            return commons_images

    # Fetch from API
    commons_images = _fetch_commons_images_direct(person_name, limit)
    return commons_images


def ensure_cache(person_id: str, title: str, person_name: Optional[str] = None) -> None:
    """Ensure cache exists for a person, fetching if necessary."""
    if cache_exists(person_id):
        print(f"Cache already exists for '{person_id}'")
        return

    print(f"Fetching Wikipedia materials for '{person_id}'...")

    # Fetch all materials
    print(f"  - Fetching Wikipedia page for '{title}' (checking EN and DE)...")
    page_data = _fetch_wikipedia_page_direct(title)
    source_lang = page_data.get("_source_language", "en")
    print(
        f"    Using {source_lang.upper()} version ({len(page_data.get('extract', ''))} characters)"
    )

    print("  - Fetching Wikipedia summary (checking EN and DE)...")
    summary_data = _fetch_wikipedia_summary_direct(title)
    summary_lang = summary_data.get("_source_language", "en")
    if summary_data:
        print(f"    Using {summary_lang.upper()} version")

    # Use person_name if provided, otherwise use page title
    search_name = person_name or page_data.get("title", title)
    print(f"  - Fetching Commons images for '{search_name}'...")
    commons_images = _fetch_commons_images_direct(search_name, limit=30)

    # Save to cache
    print("  - Saving to cache...")
    save_cache(person_id, page_data, summary_data, commons_images)
    print(f"Cache created for '{person_id}' with {len(commons_images)} Commons images")
