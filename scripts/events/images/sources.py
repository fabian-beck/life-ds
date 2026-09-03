"""The two services the pipeline asks for pictures, and what they answer with.

Commons is searched directly and answers with the metadata the quality filter
reads—pixel dimensions, byte size, MIME type, categories, and the two dates
that place a photograph relative to the event. Openverse is the breadth behind
it, aggregating Flickr, museums, and other collections; it indexes Commons too,
so its Commons results are dropped rather than deduplicated, because the same
file surfaces under a URL form an exact-URL comparison cannot match.

Both return the same candidate shape, so the pool they build can be scored and
ranked as one.
"""

from typing import Any, Dict, List

import requests

from utils.http import QueryParams, canonical_commons_url
from utils.wikipedia_cache import _strip_html_tags, wikipedia_headers


def search_wikimedia_commons(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search Wikimedia Commons using MediaWiki API.

    Returns list of image metadata dicts with url, caption, source, filename,
    and quality metrics (width, height, size, mime, dates, categories).
    """
    api_url = "https://commons.wikimedia.org/w/api.php"

    params: QueryParams = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap|drawing {query}",
        "gsrnamespace": 6,  # File namespace
        "gsrlimit": limit,
        "prop": "imageinfo|categories",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 800,
        "cllimit": 50,  # Get up to 50 categories per image
    }

    try:
        response = requests.get(
            api_url, params=params, timeout=30, headers=wikipedia_headers()
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"    Commons API error for '{query}': {e}")
        return []

    pages = data.get("query", {}).get("pages", {})
    images = []

    for page_id, page_data in pages.items():
        image_info = page_data.get("imageinfo", [{}])[0]

        # For SVGs, prefer thumburl (PNG render) over url (raw SVG)
        # thumburl is provided when iiurlwidth is set
        url = canonical_commons_url(image_info.get("thumburl") or image_info.get("url"))

        if not url:
            continue

        # Extract filename from page title
        filename = page_data.get("title", "").replace("File:", "")

        # Extract quality metrics
        width = image_info.get("width", 0)
        height = image_info.get("height", 0)
        file_size = image_info.get("size", 0)
        mime_type = image_info.get("mime", "")

        # Extract caption and attribution from metadata
        extmetadata = image_info.get("extmetadata", {})
        caption = (
            extmetadata.get("ImageDescription", {}).get("value", "")
            or extmetadata.get("ObjectName", {}).get("value", "")
            or filename
        )
        caption = _strip_html_tags(caption)

        # Extract creator (artist)
        creator_raw = extmetadata.get("Artist", {}).get("value", "")
        creator = _strip_html_tags(creator_raw) if creator_raw else None

        # Extract license info
        license_name = extmetadata.get("LicenseShortName", {}).get("value", "")
        license_url = extmetadata.get("LicenseUrl", {}).get("value", "")

        # Extract temporal metadata
        date_time_original = extmetadata.get("DateTimeOriginal", {}).get("value", "")
        date_time_upload = extmetadata.get("DateTime", {}).get("value", "")

        # Extract categories
        categories_raw = page_data.get("categories", [])
        categories = [
            cat.get("title", "").replace("Category:", "") for cat in categories_raw
        ]

        # Build source URL
        source = f"https://commons.wikimedia.org/wiki/{page_data.get('title', '').replace(' ', '_')}"

        images.append(
            {
                "url": url,
                "filename": filename,
                "caption": caption,
                "source": source,
                "creator": creator,
                "license": license_name if license_name else None,
                "licenseUrl": license_url if license_url else None,
                # Quality metrics
                "width": width,
                "height": height,
                "size": file_size,
                "mime": mime_type,
                "dateTimeOriginal": date_time_original,
                "dateTimeUpload": date_time_upload,
                "categories": categories,
            }
        )

    return images


def search_openverse(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search Openverse API for CC-licensed images.

    Openverse aggregates images from Flickr, Wikimedia, museums, and other sources.
    Returns list of image metadata dicts with url, caption, source, filename.
    """
    api_url = "https://api.openverse.org/v1/images/"

    params: QueryParams = {
        "q": query,
        "page_size": limit,
        # Filter for licenses that allow reuse
        "license_type": "commercial,modification",
    }

    headers = {"User-Agent": "life-ds-project/1.0 (biographical timeline generator)"}

    try:
        response = requests.get(api_url, params=params, timeout=30, headers=headers)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"    Openverse API error for '{query}': {e}")
        return []

    results = data.get("results", [])
    images = []

    for item in results:
        url = item.get("url")
        if not url:
            continue

        # Openverse indexes Wikimedia Commons too, but the pipeline already
        # searches Commons directly — and the same file surfaces here under a
        # different URL form, which the exact-URL dedup cannot catch. Keep only
        # the providers the Commons search cannot supply.
        if item.get("provider") == "wikimedia":
            continue

        # Extract filename from URL or title
        title = item.get("title", "")
        filename = title or url.split("/")[-1]

        # Use title as caption, fall back to attribution
        caption = title or item.get("attribution", filename)

        # Source is the foreign landing URL (original page)
        source = item.get("foreign_landing_url", url)

        # Add provider info to help with deduplication
        provider = item.get("provider", "openverse")

        # Extract creator and license info
        creator = item.get("creator")
        license_code = item.get("license", "")
        license_version = item.get("license_version", "")
        license_url = item.get("license_url", "")

        # Format license name (e.g., "by-sa" + "3.0" -> "CC BY-SA 3.0")
        license_name = None
        if license_code:
            license_name = f"CC {license_code.upper()}"
            if license_version:
                license_name += f" {license_version}"

        images.append(
            {
                "url": url,
                "filename": filename,
                "caption": caption,
                "source": source,
                "provider": provider,
                "creator": creator,
                "license": license_name,
                "licenseUrl": license_url if license_url else None,
                # The quality filter reads these; a candidate without them was
                # scored as 0×0 pixels and rejected before any scoring ran.
                # Flickr and museum providers report no filesize or filetype,
                # so those stay 0/empty and the filter must treat them as
                # unknown rather than as too small.
                "width": item.get("width") or 0,
                "height": item.get("height") or 0,
                "size": item.get("filesize") or 0,
                "mime": (f"image/{item['filetype']}" if item.get("filetype") else ""),
            }
        )

    return images
