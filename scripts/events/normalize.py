"""Bring what a model wrote into the shape the corpus is read with.

Two passes, and the second is the one that matters. The helpers normalize a
value at a time: a date to ISO-8601 at the precision it was given, a name to
the one form the registries and the localized files must agree on, a quoted
string to its content. `enforce_metadata` then walks a finished payload and
applies them in order—the person's name, the dates, the portrait, the
locations, the images, the annotations and chapters—and ends by replacing the
control characters a model writes where typographic punctuation belongs.

Nothing here calls a model or reads the network. That is what lets the whole
of it be exercised without either.
"""

import re
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from utils.text import fix_control_characters
from utils.word_overlap import restates
from utils.wikipedia_cache import _strip_html_tags

DATASET_NAME = "Life Data Stories"


def _strip_wrapping_quotes(value: str) -> str:
    trimmed = value.strip()
    quotes = "\"'" "''"
    while len(trimmed) >= 2 and trimmed[0] in quotes and trimmed[-1] in quotes:
        trimmed = trimmed[1:-1].strip()
    return trimmed


def _clean_date_note_text(note: str) -> str:
    cleaned = note.strip()
    prefix_patterns = [
        r"^Described in the source as\s+",
        r"^Described as\s+",
        r"^Documented as\s+",
        r"^Recorded as\s+",
        r"^Listed as\s+",
        r"^Reported as\s+",
        r"^Referenced as\s+",
        r"^(?:The\s+)?source\s+(?:notes|indicates|describes|lists|states)\s+(?:that\s+|it\s+as\s+)?",
        r"^(?:According to|Per)\s+the\s+source,\s*",
    ]
    for pattern in prefix_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = _strip_wrapping_quotes(cleaned)
    cleaned = cleaned.rstrip(" .:;")
    return cleaned.strip()


def _split_date_annotation(value: str) -> Tuple[str, Optional[str], bool]:
    text = value.strip()
    prefer_note = False
    note = None
    match = re.match(r"^(.*?)\(([^()]*)\)\s*$", text)
    if match:
        base = match.group(1).strip(",; ")
        note_candidate = _clean_date_note_text(match.group(2))
        if note_candidate:
            note = note_candidate
            prefer_note = True
        text = base or text
    return text.strip(), note, prefer_note


def _clean_candidate_name(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    cleaned = _strip_html_tags(value)
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:\u00b7")
    return cleaned or None


def _collect_person_name_candidates(
    person: Dict[str, Any],
    page_data: Dict[str, Any],
    summary_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def push(raw: Optional[str]) -> None:
        cleaned = _clean_candidate_name(raw)
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(cleaned)

        if "," in cleaned:
            primary = cleaned.split(",", 1)[0].strip()
            primary_clean = _clean_candidate_name(primary)
            if primary_clean:
                primary_key = primary_clean.casefold()
                if primary_key not in seen:
                    seen.add(primary_key)
                    candidates.append(primary_clean)

        simplified_parentheses = _clean_candidate_name(
            re.sub(r"\s*\([^)]*\)", "", cleaned).strip()
        )
        if simplified_parentheses:
            simple_key = simplified_parentheses.casefold()
            if simple_key not in seen:
                seen.add(simple_key)
                candidates.append(simplified_parentheses)

    push(person.get("name"))
    push(person.get("preferred_name"))
    push(page_data.get("title"))
    push(page_data.get("displaytitle"))

    if summary_data:
        push(summary_data.get("title"))
        push(summary_data.get("displaytitle"))
        titles = summary_data.get("titles")
        if isinstance(titles, dict):
            for value in titles.values():
                push(value)

    return candidates


def _name_score(value: str) -> Tuple[int, int, int]:
    punctuation_penalty = 0
    for symbol, weight in ((",", 3), ("(", 2), (")", 2), (";", 1), (":", 1)):
        punctuation_penalty += value.count(symbol) * weight
    word_count = len(value.split())
    length_penalty = len(value)
    return punctuation_penalty, word_count, length_penalty


def normalize_date_value(value: Optional[str], precision: str) -> tuple[Any, str]:
    if value is None:
        return None, precision
    sanitized = str(value).strip()
    if not sanitized:
        return None, precision
    level = precision.lower()
    if level not in {"day", "month", "year"}:
        level = "day"

    if level == "day":
        candidate = sanitized[:10]
        try:
            datetime.strptime(candidate, "%Y-%m-%d")
            return candidate, "day"
        except ValueError:
            level = "month"

    if level == "month":
        candidate = sanitized[:7]
        try:
            datetime.strptime(candidate, "%Y-%m")
            return candidate, "month"
        except ValueError:
            level = "year"

    match = re.search(r"\d{4}", sanitized)
    if match:
        return match.group(0), "year"

    return None, "unknown"


def normalize_date_for_comparison(date_str: str, to_end: bool = False) -> str:
    """
    Normalize a partial date string for comparison.

    Dates can have different precisions (year, month, day). When comparing
    dates for chapter assignment, we need to expand partial dates to full
    dates to ensure correct comparison.

    Args:
        date_str: Date like "1945", "1945-07", or "1945-07-01"
        to_end: If True, pad to end of period; if False, pad to start

    Returns:
        Full date string in "YYYY-MM-DD" format

    Examples:
        normalize_date_for_comparison("1945", to_end=False) -> "1945-01-01"
        normalize_date_for_comparison("1945", to_end=True) -> "1945-12-31"
        normalize_date_for_comparison("1945-07", to_end=False) -> "1945-07-01"
        normalize_date_for_comparison("1945-07", to_end=True) -> "1945-07-31"
    """
    if not date_str:
        return "9999-12-31" if to_end else "0000-01-01"

    parts = date_str.split("-")
    if len(parts) == 1:  # Year only
        return f"{parts[0]}-12-31" if to_end else f"{parts[0]}-01-01"
    elif len(parts) == 2:  # Year-month
        if to_end:
            # Get last day of month
            year, month = int(parts[0]), int(parts[1])
            last_day = monthrange(year, month)[1]
            return f"{parts[0]}-{parts[1]}-{last_day:02d}"
        else:
            return f"{parts[0]}-{parts[1]}-01"
    return date_str  # Already full date


def event_sort_key(event: Dict[str, Any]) -> str:
    date_value = event.get("date")
    precision = (event.get("date_precision") or "day").lower()
    if not date_value:
        return "9999-12-31"
    if precision == "year":
        return f"{date_value}-12-31"
    if precision == "month":
        return f"{date_value}-28"
    return str(date_value)


_ANNOTATION_MARKER = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _term_words(term: str) -> str:
    """A term as it reads in prose: slugged keys spaced out, case folded."""
    return re.sub(r"\s+", " ", term.replace("_", " ")).strip().casefold()


def _names_term(text: str, term: str) -> bool:
    words = _term_words(term)
    return bool(words) and (
        re.search(rf"(?<!\w){re.escape(words)}(?!\w)", _term_words(text)) is not None
    )


def _unwrap_marker(description: str, term: str) -> str:
    """Reduce this term's `[[term|display]]` markup to its display text."""
    return _ANNOTATION_MARKER.sub(
        lambda m: ((m.group(2) or m.group(1)) if m.group(1) == term else m.group(0)),
        description,
    )


def drop_annotation(event: Dict[str, Any], term: str) -> None:
    """Remove one term's annotation and unwrap its marker in the description."""
    annotations = event.get("annotations")
    if isinstance(annotations, dict):
        annotations.pop(term, None)
        if not annotations:
            event.pop("annotations", None)
    description = event.get("description")
    if isinstance(description, str):
        event["description"] = _unwrap_marker(description, term)


def _classification_subject(event: Dict[str, Any]) -> Optional[str]:
    """The name the event's classification card explains, if it has one."""
    event_class = event.get("event_class")
    title = event_class.get("title") if isinstance(event_class, dict) else None
    if not isinstance(title, str) or not title.strip():
        return None
    # "Zahlbericht (report on algebraic number theory)" names the Zahlbericht.
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip() or None


def drop_classified_annotations(events: List[Dict[str, Any]]) -> List[str]:
    """Drop a gloss of what the event's own classification card explains.

    An invention or publication event carries a card under its description
    that names its subject and says what it is. The research is told not to
    annotate that subject, and does anyway: Turing's Bombe slide glossed
    "bombe" in the sentence directly above a card headed "Bombe" that says
    the same thing. An annotation is dropped when its term is the whole
    classification title (a trailing parenthetical aside), and its markup
    unwrapped. A term that only sits inside a longer title stays, since a
    card about "On Computable Numbers" does not explain the
    Entscheidungsproblem. Returns the dropped terms.
    """
    dropped: List[str] = []
    for event in events:
        subject = _classification_subject(event)
        annotations = event.get("annotations")
        if not subject or not isinstance(annotations, dict):
            continue
        for term in list(annotations):
            if _term_words(term) == _term_words(subject):
                drop_annotation(event, term)
                dropped.append(term)
    return dropped


def drop_repeated_annotations(events: List[Dict[str, Any]]) -> List[str]:
    """Explain a term once, where the story first makes it a subject.

    The research takes each event on its own, so nothing tells the call that
    the Analytical Engine already had a slide of its own three events back;
    it glosses the term again, and the reader who followed the story is
    offered a definition of what they just read about. A term counts as
    introduced once an earlier event annotated it or named it in its title
    or its classification's title. A later annotation of that term is
    removed and its `[[term|display]]` markup unwrapped to the display text.
    Events must already be in story order. Returns the dropped terms.
    """
    introduced: List[str] = []
    dropped: List[str] = []
    for event in events:
        annotations = event.get("annotations")
        if isinstance(annotations, dict):
            for term in list(annotations):
                if not any(_names_term(text, term) for text in introduced):
                    continue
                drop_annotation(event, term)
                dropped.append(term)
            if event.get("annotations"):
                introduced.extend(event["annotations"])
        for text in (
            event.get("title"),
            (
                (event.get("event_class") or {}).get("title")
                if isinstance(event.get("event_class"), dict)
                else None
            ),
        ):
            if isinstance(text, str) and text.strip():
                introduced.append(text)
    return dropped


def drop_restating_annotations(events: List[Dict[str, Any]]) -> List[str]:
    """Drop a gloss that says again what its own sentence already said.

    A description that introduces a term in an appositive has defined it:
    "reported to Bletchley Park, the wartime center of the British codebreaking
    organization" leaves a popup reading "Bletchley Park was the British
    wartime codebreaking center" with nothing to tell. The research is told
    that such a sentence defines its term, and the review is told to drop the
    gloss, and both still write them — a Turing dataset generated from scratch
    under those prompts shipped five.

    The rule is lexical, so it holds without a model: an explanation whose
    content words mostly already stand in the title, the description, or the
    term itself is dropped and its markup unwrapped. A paraphrase that reaches
    past the sentence keeps its words and stays. `validate_event_prose.py`
    reports what shipped before this ran, under the same rule. Returns the
    dropped terms.
    """
    dropped: List[str] = []
    for event in events:
        annotations = event.get("annotations")
        if not isinstance(annotations, dict):
            continue
        context = f"{event.get('title') or ''} {event.get('description') or ''}"
        for term in list(annotations):
            explanation = str((annotations.get(term) or {}).get("explanation") or "")
            if restates(explanation, context, term):
                drop_annotation(event, term)
                dropped.append(term)
    return dropped


def _upper_bound_date(value: Optional[str], precision: str) -> Optional[date]:
    """Convert varying precision date strings into a comparable upper bound."""
    if not value:
        return None
    normalized_precision = (precision or "day").lower()
    try:
        if normalized_precision == "day":
            return datetime.strptime(value, "%Y-%m-%d").date()
        if normalized_precision == "month":
            year, month = [int(part) for part in value.split("-")[:2]]
            last_day = monthrange(year, month)[1]
            return date(year, month, last_day)
        if normalized_precision == "year":
            year = int(value[:4])
            return date(year, 12, 31)
    except (ValueError, TypeError):
        return None
    return None


def _clean_all_strings(data: Any) -> Any:
    """
    Recursively fix control characters in all strings within a data structure.

    This ensures AI-generated text doesn't contain incorrect Unicode control
    characters that should be typographic punctuation.
    """
    if isinstance(data, dict):
        return {key: _clean_all_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_clean_all_strings(item) for item in data]
    elif isinstance(data, str):
        return fix_control_characters(data)
    else:
        return data


def enforce_metadata(
    payload: Dict[str, Any],
    page_data: Dict[str, Any],
    summary_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize and enforce metadata standards."""
    payload.setdefault("dataset", DATASET_NAME)
    payload["created_on"] = date.today().isoformat()

    person = payload.setdefault("person", {})
    name_candidates = _collect_person_name_candidates(person, page_data, summary_data)
    if name_candidates:
        preferred_name = min(name_candidates, key=_name_score)
        person["name"] = preferred_name
    else:
        person.setdefault("name", page_data.get("title"))

    for key in ("birth_date", "death_date"):
        value = person.get(key)
        if value:
            normalized, normalized_precision = normalize_date_value(value, "day")
            if normalized and normalized_precision == "day":
                person[key] = normalized
            elif normalized:
                suffix = "-01-01" if normalized_precision == "year" else "-01"
                person[key] = f"{normalized}{suffix}"
            else:
                person[key] = None

    if page_data.get("fullurl"):
        person.setdefault("wikipedia", page_data["fullurl"])

    # Only set Wikipedia portrait if we don't already have a generated portrait
    # (generated portraits have image paths starting with /portraits/)
    existing_portrait = person.get("portrait", {})
    has_generated_portrait = (
        isinstance(existing_portrait, dict)
        and isinstance(existing_portrait.get("image"), str)
        and existing_portrait["image"].startswith("/portraits/")
    )

    if not has_generated_portrait:
        # No generated portrait - use Wikipedia page image if available
        original = page_data.get("original", {})
        if original:
            # Extract image URL from Wikipedia's pageimages API response
            image_url = original.get("source")
            if image_url:
                person["portrait"] = {
                    "image": image_url,
                    "source": page_data.get("fullurl"),
                }
        # If no portrait from Wikipedia API, ensure portrait is None or has proper structure
        if not person.get("portrait") or (
            isinstance(person.get("portrait"), dict)
            and person["portrait"].get("image") is None
        ):
            person["portrait"] = None

    death_cutoff: Optional[date] = None
    death_value = person.get("death_date")
    if isinstance(death_value, str):
        try:
            death_cutoff = datetime.strptime(death_value, "%Y-%m-%d").date()
        except ValueError:
            death_cutoff = None

    events = []
    for event in payload.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        event = {**event}

        note_values: List[str] = []

        def add_note(candidate: Optional[str]) -> None:
            if not candidate:
                return
            if candidate in note_values:
                return
            note_values.append(candidate)

        raw_start_date = event.get("date")
        start_input = raw_start_date
        prefer_note_label = False
        if isinstance(raw_start_date, str):
            start_input, start_note, prefer_note_label = _split_date_annotation(
                raw_start_date
            )
            add_note(start_note)

        precision_value = event.get("date_precision") or "day"
        normalized_date, normalized_precision = normalize_date_value(
            start_input, precision_value
        )
        if not normalized_date:
            continue
        event["date"] = normalized_date
        event["date_precision"] = normalized_precision

        raw_date_end = event.get("date_end") or event.get("end_date")
        end_input = raw_date_end
        if isinstance(raw_date_end, str):
            end_input, end_note, _ = _split_date_annotation(raw_date_end)
            add_note(end_note)

        raw_date_end_precision = (
            event.get("date_end_precision")
            or event.get("end_date_precision")
            or precision_value
        )
        normalized_end_date = None
        normalized_end_precision = raw_date_end_precision
        if end_input:
            normalized_end_date, normalized_end_precision = normalize_date_value(
                end_input, raw_date_end_precision or normalized_precision
            )
        if normalized_end_date:
            event["date_end"] = normalized_end_date
            event["date_end_precision"] = normalized_end_precision
        else:
            event.pop("date_end", None)
            event.pop("date_end_precision", None)
        event.pop("end_date", None)
        event.pop("end_date_precision", None)

        if death_cutoff is not None:
            comparison_date = normalized_end_date or normalized_date
            comparison_precision = normalized_end_precision or normalized_precision
            upper_bound = _upper_bound_date(comparison_date, comparison_precision)
            if upper_bound and upper_bound > death_cutoff:
                continue

        existing_note_raw = event.get("date_note")
        cleaned_existing_note = None
        if isinstance(existing_note_raw, str):
            cleaned_existing_note = (
                _clean_date_note_text(existing_note_raw) or existing_note_raw.strip()
            )
        add_note(cleaned_existing_note)

        if note_values:
            note_output = (
                "; ".join(note_values) if len(note_values) > 1 else note_values[0]
            )
            event["date_note"] = note_output
            if prefer_note_label:
                event["date_label"] = note_values[0]
            else:
                event.pop("date_label", None)
        else:
            event.pop("date_note", None)
            event.pop("date_label", None)

        # Validate locations array
        raw_locations = event.get("locations") or []
        sanitized_locations = []

        for loc in raw_locations:
            if not isinstance(loc, dict):
                continue

            name_historic = (
                loc.get("name_historic", "").strip()
                if loc.get("name_historic")
                else None
            )
            name_modern = (
                loc.get("name_modern", "").strip() if loc.get("name_modern") else None
            )
            centroid = loc.get("centroid")

            # Validate centroid if present
            valid_centroid = None
            if isinstance(centroid, list) and len(centroid) == 2:
                try:
                    lon, lat = float(centroid[0]), float(centroid[1])
                    if -180 <= lon <= 180 and -90 <= lat <= 90:
                        valid_centroid = [lon, lat]
                except (TypeError, ValueError):
                    pass

            # Include if has historic name
            if name_historic:
                sanitized_locations.append(
                    {
                        "name_historic": name_historic,
                        "name_modern": name_modern,
                        "centroid": valid_centroid,
                        "primary": bool(loc.get("primary", False)),
                    }
                )

        event["locations"] = sanitized_locations

        # Handle images
        raw_images = event.get("images") or []
        sanitized_images = []
        seen_images: Set[str] = set()
        if isinstance(raw_images, list):
            for image_data in raw_images:
                if isinstance(image_data, dict):
                    image_url = image_data.get("url", "").strip()
                    caption = image_data.get("caption", "").strip()
                    source = image_data.get("source", "").strip()

                    if not image_url or not (
                        image_url.startswith("http://")
                        or image_url.startswith("https://")
                    ):
                        continue

                    key = image_url.casefold()
                    if key in seen_images:
                        continue
                    seen_images.add(key)

                    sanitized_images.append(
                        {
                            "url": image_url,
                            "caption": caption or "Image from Wikimedia Commons",
                            "source": source or None,
                            # Attribution is a license condition for the CC
                            # BY-SA material here, so it survives sanitizing.
                            "creator": image_data.get("creator") or None,
                            "license": image_data.get("license") or None,
                            "licenseUrl": image_data.get("licenseUrl") or None,
                        }
                    )
        # Enforce maximum of one image per event
        if sanitized_images:
            event["images"] = sanitized_images[:1]
        else:
            event.pop("images", None)

        # Validate annotations
        raw_annotations = event.get("annotations")
        if raw_annotations and isinstance(raw_annotations, dict):
            sanitized_annotations = {}
            for term_key, annotation in raw_annotations.items():
                if isinstance(annotation, dict):
                    explanation = annotation.get("explanation", "").strip()
                    wikipedia_url = (
                        annotation.get("wikipedia_url", "").strip()
                        if annotation.get("wikipedia_url")
                        else None
                    )

                    # Only keep annotations with valid explanations
                    if explanation:
                        sanitized_annotations[term_key] = {"explanation": explanation}
                        if wikipedia_url and (
                            wikipedia_url.startswith("http://")
                            or wikipedia_url.startswith("https://")
                        ):
                            sanitized_annotations[term_key][
                                "wikipedia_url"
                            ] = wikipedia_url

            if sanitized_annotations:
                event["annotations"] = sanitized_annotations
            else:
                event.pop("annotations", None)
        else:
            event.pop("annotations", None)

        events.append(event)

    events.sort(key=event_sort_key)
    drop_classified_annotations(events)
    drop_repeated_annotations(events)
    drop_restating_annotations(events)
    payload["events"] = events

    # Process chapters if present
    raw_chapters = payload.get("chapters")
    if raw_chapters and isinstance(raw_chapters, list):
        chapters = []
        for chapter in raw_chapters:
            if not isinstance(chapter, dict):
                continue
            chapter = {**chapter}

            # Normalize chapter start date
            start_date = chapter.get("date_start")
            start_precision = chapter.get("date_start_precision") or "year"
            normalized_start, normalized_start_precision = normalize_date_value(
                start_date, start_precision
            )
            if normalized_start:
                chapter["date_start"] = normalized_start
                chapter["date_start_precision"] = normalized_start_precision
            else:
                continue

            # Normalize chapter end date
            end_date = chapter.get("date_end")
            end_precision = chapter.get("date_end_precision") or "year"
            normalized_end, normalized_end_precision = normalize_date_value(
                end_date, end_precision
            )
            if normalized_end:
                chapter["date_end"] = normalized_end
                chapter["date_end_precision"] = normalized_end_precision
            else:
                continue

            chapters.append(chapter)

        if chapters:
            chapters.sort(key=lambda c: c.get("date_start", "9999"))
            payload["chapters"] = chapters
        else:
            payload.pop("chapters", None)
    else:
        payload.pop("chapters", None)

    # Fix any control characters in all strings throughout the payload
    payload = _clean_all_strings(payload)

    return payload
