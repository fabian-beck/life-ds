"""Rank retrieved image candidates before a model is asked to place them.

The searches return far more pictures than any life needs, and most of them
are unusable for a reason a filename or a pixel count already shows: a
thumbnail, an extreme crop, a logo in SVG. Scoring drops those and orders what
is left, so the matching call spends its context on candidates rather than on
noise.

The scores are pure functions of the metadata each source reports, which is
what lets them run once over the whole pool and serve every event from it.
"""

import re
from typing import Any, Dict, List, Optional


def parse_year_from_date_string(date_str: str) -> Optional[int]:
    """
    Extract year from various date string formats.

    Handles formats like:
    - "2020-05-15" (ISO)
    - "15 May 2020" (human readable)
    - "2020" (year only)
    - "1912-06-23 00:00:00" (with time)
    """
    if not date_str:
        return None

    # Try to extract 4-digit year
    year_match = re.search(r"\b(1\d{3}|20\d{2})\b", date_str)
    if year_match:
        return int(year_match.group(1))

    return None


def score_resolution(width: int, height: int) -> float:
    """
    Score image resolution (0-10 points).

    Higher resolution = better quality for display.
    """
    if width <= 0 or height <= 0:
        return 0.0

    pixels = width * height

    if pixels >= 4_000_000:  # 4+ MP
        return 10.0
    elif pixels >= 2_000_000:  # 2-4 MP
        return 8.0
    elif pixels >= 1_000_000:  # 1-2 MP
        return 6.0
    elif pixels >= 500_000:  # 0.5-1 MP
        return 4.0
    else:  # <0.5 MP
        return 2.0


def score_file_efficiency(file_size: int, width: int, height: int) -> float:
    """
    Score file size efficiency (0-5 points).

    Detects overly compressed (lossy) or bloated files.
    Sweet spot: 0.5-2 bytes/pixel for JPEG.
    """
    if file_size <= 0 or width <= 0 or height <= 0:
        return 3.0  # Neutral score if data unavailable

    pixels = width * height
    bytes_per_pixel = file_size / pixels

    if 0.5 <= bytes_per_pixel <= 2.0:
        return 5.0  # Well-compressed
    elif 0.2 <= bytes_per_pixel < 0.5:
        return 3.0  # Over-compressed (potential quality loss)
    elif 2.0 < bytes_per_pixel <= 5.0:
        return 4.0  # Slightly bloated but OK
    else:
        return 1.0  # Extremely compressed or bloated


def score_temporal_relevance(
    event_date: str, image_date_original: str, image_date_upload: str
) -> float:
    """
    Score temporal relevance (0-10 points).

    Prefers:
    - Period-appropriate images (contemporary to the event)
    - Recent uploads (better scans/digitization)
    """
    event_year = parse_year_from_date_string(event_date)
    original_year = parse_year_from_date_string(image_date_original)
    upload_year = parse_year_from_date_string(image_date_upload)

    score = 0.0

    # Period-appropriate images (huge bonus)
    if original_year and event_year:
        year_diff = abs(original_year - event_year)
        if year_diff <= 5:
            score += 10.0  # Contemporary image
        elif year_diff <= 20:
            score += 7.0  # Near-contemporary
        elif year_diff <= 50:
            score += 4.0  # Same era
        elif year_diff <= 100:
            score += 2.0  # Within lifetime

    # Recent uploads bonus (better scans/digitization)
    if upload_year:
        if upload_year >= 2020:
            score += 3.0  # Very recent upload
        elif upload_year >= 2015:
            score += 2.0  # Recent upload
        elif upload_year >= 2010:
            score += 1.0  # Modern upload

    return min(score, 10.0)  # Cap at 10


def extract_keywords_from_text(text: str, min_length: int = 4) -> List[str]:
    """
    Extract meaningful keywords from text.

    Filters out common words and keeps substantive terms.
    """
    if not text:
        return []

    # Common stopwords to filter out
    stopwords = {
        "the",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "a",
        "an",
    }

    # Extract words, lowercase, filter by length and stopwords
    words = re.findall(r"\b\w+\b", text.lower())
    keywords = [w for w in words if len(w) >= min_length and w not in stopwords]

    return list(set(keywords))  # Unique keywords


def score_categories(
    categories: List[str], person_name: str, event_keywords: List[str]
) -> float:
    """
    Score category relevance (0-5 points).

    Uses Wikimedia Commons categories to assess relevance.
    """
    if not categories:
        return 0.0

    score = 0.0
    categories_lower = [c.lower() for c in categories]

    # Person name in categories
    person_name_parts = person_name.lower().split()
    for part in person_name_parts:
        if len(part) >= 3:  # Skip very short name parts
            if any(part in cat for cat in categories_lower):
                score += 2.0
                break

    # Event keywords in categories
    for keyword in event_keywords[:10]:  # Check first 10 keywords
        if any(keyword in cat for cat in categories_lower):
            score += 1.0
            break

    # Penalty for modern/generic categories
    penalty_categories = [
        "modern",
        "statue",
        "monument",
        "memorial",
        "plaque",
        "street",
        "postage",
        "stamp",
    ]
    for penalty in penalty_categories:
        if any(penalty in cat for cat in categories_lower):
            score -= 2.0
            break

    return max(0.0, min(score, 5.0))  # Clamp to 0-5


def score_filename(filename: str) -> float:
    """
    Score filename informativeness (0-5 points).

    Penalizes auto-generated names, rewards descriptive names.
    """
    if not filename:
        return 3.0  # Neutral

    score = 3.0  # Start neutral
    filename_lower = filename.lower()

    # Penalize generic/auto-generated names
    if re.match(r"^[a-f0-9]{32}", filename_lower):  # MD5 hash
        score -= 2.0
    elif re.match(r"^\d{8}_\d{6}", filename_lower):  # Timestamp only
        score -= 2.0
    elif re.match(r"^img_\d+|dsc_\d+|image\d+", filename_lower):
        score -= 1.0

    # Reward descriptive names (multiple words)
    word_count = (
        len(filename.split("_")) + len(filename.split()) + len(filename.split("-"))
    )
    if word_count >= 5:
        score += 2.0

    # Penalize likely screenshots/crops
    if "screenshot" in filename_lower or "crop" in filename_lower:
        score -= 2.0

    return max(0.0, min(score, 5.0))  # Clamp to 0-5


def calculate_image_quality_score(
    image_metadata: Dict[str, Any],
    person_name: str = "",
    event_date: str = "",
    event_text: str = "",
) -> float:
    """
    Calculate overall image quality score (0-45 points).

    Combines multiple quality metrics:
    - Resolution (0-10)
    - File efficiency (0-5)
    - Filename quality (0-5)
    - Temporal relevance (0-10, if event data provided)
    - Category relevance (0-5, if event data provided)
    - Hard filters (aspect ratio, file size, MIME type)

    Returns score (higher is better), or -1 if image fails hard filters.
    """
    width = image_metadata.get("width", 0)
    height = image_metadata.get("height", 0)
    file_size = image_metadata.get("size", 0)
    mime_type = image_metadata.get("mime", "")

    # Hard filters (permissive thresholds based on user preference)
    MIN_WIDTH = 400
    MIN_HEIGHT = 300
    MIN_PIXELS = 120_000  # 400×300 minimum
    MIN_ASPECT_RATIO = 0.3
    MAX_ASPECT_RATIO = 3.0
    MIN_FILE_SIZE = 10_000  # 10 KB
    MAX_FILE_SIZE = 50_000_000  # 50 MB

    # Check hard filters
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        return -1.0  # Too small

    if width * height < MIN_PIXELS:
        return -1.0  # Too few pixels

    aspect_ratio = width / height if height > 0 else 0
    if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
        return -1.0  # Extreme aspect ratio

    # A hard filter only when the source reports a size: Openverse returns no
    # filesize for Flickr and museum providers, and an unknown size read as 0
    # rejected every candidate they contributed.
    if file_size > 0 and (file_size < MIN_FILE_SIZE or file_size > MAX_FILE_SIZE):
        return -1.0  # File size out of range

    # Strongly prefer JPEG/PNG, but don't reject others (permissive)
    if mime_type == "image/svg+xml":
        return -1.0  # SVGs are usually logos/diagrams

    # Calculate quality scores
    score = 0.0
    score += score_resolution(width, height)
    score += score_file_efficiency(file_size, width, height)
    score += score_filename(image_metadata.get("filename", ""))

    # Add event-specific scores if provided
    if event_date or event_text:
        score += score_temporal_relevance(
            event_date,
            image_metadata.get("dateTimeOriginal", ""),
            image_metadata.get("dateTimeUpload", ""),
        )

        if person_name and event_text:
            event_keywords = extract_keywords_from_text(event_text)
            score += score_categories(
                image_metadata.get("categories", []), person_name, event_keywords
            )

    return score


def filter_images_by_quality(
    images: List[Dict[str, Any]],
    person_name: str = "",
    event_date: str = "",
    event_text: str = "",
    min_score: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Filter images by quality score, keeping only those above threshold.

    Args:
        images: List of image metadata dicts
        person_name: Person's name for category matching
        event_date: Event date for temporal relevance
        event_text: Event title + description for keyword extraction
        min_score: Minimum quality score (default: 10.0 out of 45)

    Returns:
        Filtered list of images with quality scores attached.
    """
    filtered = []

    for img in images:
        score = calculate_image_quality_score(
            img, person_name=person_name, event_date=event_date, event_text=event_text
        )

        if score >= min_score:
            # Attach score to image metadata for debugging/logging
            img["quality_score"] = score
            filtered.append(img)

    # Sort by quality score (descending)
    filtered.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

    return filtered
