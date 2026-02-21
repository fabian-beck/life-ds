#!/usr/bin/env python3
"""Standalone script to pre-fetch and cache Wikipedia materials for a person."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

from openai import OpenAI
from pydantic import BaseModel, Field

from config import DEFAULT_MODEL, DEFAULT_REASONING_EFFORT, LOW_REASONING_EFFORT
from utils.wikipedia_cache import (
    cache_exists,
    ensure_cache,
    get_cache_dir,
    get_cached_wikipedia_page,
    slugify,
    wikipedia_headers,
    _fetch_wikipedia_page_direct,
)
from utils.deutsche_biographie import ensure_deutsche_biographie_cache
import requests

MEDIAWIKI_API = "https://en.wikipedia.org/w/api.php"
MEDIAWIKI_API_DE = "https://de.wikipedia.org/w/api.php"


def wikipedia_search_titles(query: str, limit: int = 5) -> List[str]:
    """Search Wikipedia for page titles matching the query."""
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srnamespace": 0,
    }
    response = requests.get(
        MEDIAWIKI_API,
        params=params,
        timeout=30,
        headers=wikipedia_headers(),
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("query", {}).get("search", [])
    titles: List[str] = [item.get("title") for item in results if item.get("title")]
    suggestion = data.get("query", {}).get("searchinfo", {}).get("suggestion")
    if suggestion:
        titles.append(suggestion)
    return titles


def find_wikipedia_page(title: str) -> str:
    """Find a Wikipedia page, trying various title variants."""
    import re

    candidates: List[str] = []
    seen: Set[str] = set()
    attempted: List[str] = []

    def add_candidate(value: str) -> None:
        candidate = (value or "").strip()
        if not candidate:
            return
        key = candidate.casefold()
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    add_candidate(title)
    normalized_title = title.replace("_", " ")
    if normalized_title.casefold() != title.casefold():
        add_candidate(normalized_title)
    parenthetical = re.sub(r"\s*\([^)]*\)", "", normalized_title).strip()
    if parenthetical and parenthetical.casefold() not in {
        title.casefold(),
        normalized_title.casefold(),
    }:
        add_candidate(parenthetical)

    index = 0
    search_enqueued = False
    errors: List[str] = []

    while True:
        while index < len(candidates):
            candidate = candidates[index]
            index += 1
            attempted.append(candidate)
            try:
                page = _fetch_wikipedia_page_direct(candidate)
                # Return the canonical title from the page
                return page.get("title", candidate)
            except ValueError as error:
                errors.append(str(error))

        if search_enqueued:
            break

        search_enqueued = True
        for suggestion in wikipedia_search_titles(title):
            add_candidate(suggestion)

    attempted_titles = ", ".join(attempted) if attempted else title
    error_details = "; ".join(dict.fromkeys(errors)) if errors else ""
    message = (
        "Unable to locate a Wikipedia page for "
        f"'{title}'. Tried titles: {attempted_titles}."
    )
    if error_details:
        message = f"{message} Details: {error_details}."
    raise ValueError(message)


def fetch_page_links(title: str, limit: int = 500) -> List[str]:
    """Fetch outgoing links from a Wikipedia page."""
    params = {
        "action": "query",
        "format": "json",
        "prop": "links",
        "titles": title,
        "pllimit": limit,
        "plnamespace": 0,  # Only main namespace (articles)
    }

    response = requests.get(
        MEDIAWIKI_API,
        params=params,
        timeout=30,
        headers=wikipedia_headers(),
    )
    response.raise_for_status()
    data = response.json()
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return []

    page = next(iter(pages.values()))
    links = page.get("links", [])

    return [link.get("title") for link in links if link.get("title")]


def should_exclude_link(link_title: str, main_title: str) -> bool:
    """Check if a link should be excluded from related articles."""
    link_lower = link_title.lower()

    # Exclude navigation/meta pages
    exclude_patterns = [
        "list o",
        "index o",
        "category:",
        "portal:",
        "wikipedia:",
        "help:",
        "template:",
        "file:",
        "user:",
        "talk:",
        "disambiguation",
        "outline o",
        "timeline o",
    ]

    for pattern in exclude_patterns:
        if pattern in link_lower:
            return True

    # Exclude the main article itself
    if link_title.lower() == main_title.lower():
        return True

    return False


class SelectedArticles(BaseModel):
    """Top selected articles for biographical context."""

    selected_titles: List[str] = Field(
        description="List of selected article titles, ordered by relevance (most relevant first)"
    )


def select_articles_with_ai(
    person_name: str,
    person_summary: str,
    candidate_titles: List[str],
    max_to_select: int,
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """Use AI to select the most relevant articles from candidates."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("    Warning: OPENAI_API_KEY not set, using simple filtering instead")
        return candidate_titles[:max_to_select]

    client = OpenAI(api_key=api_key)

    # Build prompt
    prompt = f"""You are analyzing Wikipedia articles to find the most relevant related content for a biographical article.

Subject: {person_name}
Summary: {person_summary}

Below are {len(candidate_titles)} candidate article titles that are linked from the main article.

Your task: Select the {max_to_select} MOST relevant articles for enriching the BIOGRAPHY - focus EXCLUSIVELY on articles about PEOPLE they knew and specific LIFE EVENTS they experienced.

HIGHEST PRIORITY - Select articles about:
1. **People**: Family members, spouses, children, parents, colleagues, mentors, teachers, students, collaborators, friends, rivals, patrons, employees
2. **Specific life events**: Conferences they attended, meetings, key moments, expeditions, travels, speeches, debates, trials, ceremonies
3. **Specific personal creations**: Individual books/papers/artworks/inventions they personally created (not general topics)

AVOID - Do NOT select articles about:
- General places, cities, or countries (even if they lived/worked there)
- Generic institutions, universities, or organizations (even if they worked there)
- General awards or prizes (select only if it's about a specific award ceremony/event they attended)
- General theories, concepts, or fields of study
- Broad historical movements or periods
- Abstract concepts or philosophical ideas
- General scientific/academic fields
- Generic background topics

Key question: "Is this article PRIMARILY about a specific PERSON or a specific EVENT/MOMENT in this person's life?"
- If YES (it's about a person or an event) → Select it
- If NO (it's about a place, institution, award, concept, or field) → Skip it

Examples of GOOD selections:
- "Marie Curie" (person they knew)
- "Fifth Solvay Conference" (specific event they attended)
- "Annus Mirabilis papers" (specific works they created)

Examples of BAD selections:
- "University of Zurich" (institution - too general)
- "Nobel Prize in Physics" (award - too general)
- "Bern" (place - too general)
- "Theory of Relativity" (concept - too general)

Candidate articles:
{json.dumps(candidate_titles, indent=2)}

Return exactly {max_to_select} article titles about PEOPLE and LIFE EVENTS, ordered from most to least relevant."""

    system = "You are an expert research librarian specializing in biographical context and Wikipedia article analysis."

    try:
        response = client.responses.parse(
            model=model,
            reasoning={"effort": LOW_REASONING_EFFORT},
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            text_format=SelectedArticles,
        )

        if response.status != "completed" or not response.output_parsed:
            print("    Warning: AI selection failed, using simple filtering")
            return candidate_titles[:max_to_select]

        # Extract selected titles
        selected_titles = response.output_parsed.selected_titles

        # Print selections
        print(f"    AI selected {len(selected_titles)} articles:")
        for i, title in enumerate(selected_titles, 1):
            print(f"      {i}. {title}")

        return selected_titles[:max_to_select]

    except Exception as error:
        print(f"    Warning: AI selection failed ({error}), using simple filtering")
        return candidate_titles[:max_to_select]


def fetch_related_articles(
    title: str,
    max_related: int = 15,
    model: str = DEFAULT_MODEL,
    use_cache: bool = True,
    person_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch related Wikipedia articles using AI to select the most relevant ones.

    Fetches up to 1000 linked articles from both EN and DE, filters out navigation pages,
    then uses AI to directly select the top N most relevant articles for biographical context.
    For each selected article, uses the German version if longer or if English doesn't exist.

    Args:
        title: Wikipedia article title
        max_related: Maximum number of related articles to fetch
        model: OpenAI model to use for AI selection
        use_cache: If True, use cached Wikipedia page data when available
        person_id: Optional person ID for cache lookup (if None, will slugify title)
    """
    print(f"  - Finding related articles for '{title}'...")

    # Determine person_id for cache lookup
    identifier = person_id or slugify(title)

    # First, get basic info about the person for AI selection
    print("    Fetching main article data (checking EN and DE)...")
    try:
        if use_cache:
            # Try to use cached version first
            main_page_data = get_cached_wikipedia_page(
                identifier, title, use_cache=True
            )
        else:
            main_page_data = _fetch_wikipedia_page_direct(title)

        extract = main_page_data.get("extract", "")
        source_lang = main_page_data.get("_source_language", "en")
        print(f"      Using {source_lang.upper()} version for main article")
        # Get first paragraph as summary for AI
        person_summary = extract.split("\n\n")[0] if extract else ""
    except Exception as error:
        print(f"    Warning: Could not fetch main article ({error})")
        person_summary = ""

    # Get up to 1000 links from both English and German pages
    print("    Fetching linked articles from EN and DE...")
    all_links_en = []
    all_links_de = []

    try:
        all_links_en = fetch_page_links(title, limit=1000)
    except Exception as error:
        print(f"      Warning: Could not fetch EN links ({error})")

    try:
        # Also fetch links from German version
        params = {
            "action": "query",
            "format": "json",
            "prop": "links",
            "titles": title,
            "pllimit": 1000,
            "plnamespace": 0,  # Only main namespace (articles)
        }
        response = requests.get(
            MEDIAWIKI_API_DE,
            params=params,
            timeout=30,
            headers=wikipedia_headers(),
        )
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        if pages:
            page = next(iter(pages.values()))
            links = page.get("links", [])
            all_links_de = [link.get("title") for link in links if link.get("title")]
    except Exception as error:
        print(f"      Warning: Could not fetch DE links ({error})")

    # Combine and deduplicate links
    seen_links = set()
    all_links = []
    for link in all_links_en + all_links_de:
        link_lower = link.lower()
        if link_lower not in seen_links:
            seen_links.add(link_lower)
            all_links.append(link)

    print(
        f"      Found {len(all_links_en)} EN links, {len(all_links_de)} DE links, {len(all_links)} total unique"
    )

    if not all_links:
        print("    No links found on the page")
        return []

    # Filter out excluded links
    candidate_links = [
        link_title
        for link_title in all_links
        if not should_exclude_link(link_title, title)
    ]

    print(f"    Found {len(candidate_links)} candidate articles")

    if len(candidate_links) == 0:
        return []

    # Use AI to select top articles from all candidates
    print(
        f"    Using AI to select top {max_related} from {len(candidate_links)} candidates..."
    )
    selected_titles = select_articles_with_ai(
        person_name=title,
        person_summary=person_summary,
        candidate_titles=candidate_links,
        max_to_select=max_related,
        model=model,
    )

    # Fetch full article data for selected titles (using EN/DE preference logic)
    print(
        f"    Fetching full text for {len(selected_titles)} selected articles (checking EN and DE)..."
    )
    related_articles = []
    for link_title in selected_titles:
        try:
            # Generate person_id for this related article
            related_person_id = slugify(link_title)

            # Try to use existing cache if available, but DON'T create new cache directories
            # for related articles (only the main person should get a directory)
            if use_cache:
                try:
                    # Check if cache already exists
                    if cache_exists(related_person_id):
                        # Load from existing cache
                        page_data = get_cached_wikipedia_page(
                            related_person_id, link_title, use_cache=True
                        )
                    else:
                        # No cache exists - fetch directly without creating cache
                        page_data = _fetch_wikipedia_page_direct(link_title)
                except Exception as cache_error:
                    print(
                        f"      Warning: Cache read failed for '{link_title}', fetching directly: {cache_error}"
                    )
                    page_data = _fetch_wikipedia_page_direct(link_title)
            else:
                page_data = _fetch_wikipedia_page_direct(link_title)

            extract = page_data.get("extract", "")
            source_lang = page_data.get("_source_language", "en")

            # Use first paragraph as summary (untruncated)
            summary = extract.split("\n\n")[0] if extract else ""

            # Determine URL based on source language
            if source_lang == "de":
                url = page_data.get(
                    "fullurl",
                    f"https://de.wikipedia.org/wiki/{link_title.replace(' ', '_')}",
                )
            else:
                url = page_data.get(
                    "fullurl",
                    f"https://en.wikipedia.org/wiki/{link_title.replace(' ', '_')}",
                )

            related_articles.append(
                {
                    "title": page_data.get("title", link_title),
                    "summary": summary,
                    "fullText": extract,
                    "url": url,
                    "language": source_lang,
                }
            )

        except Exception as error:
            print(f"    Warning: Failed to fetch '{link_title}': {error}")
            continue

    print(f"    Found {len(related_articles)} related articles")
    # Print language distribution
    en_count = sum(1 for a in related_articles if a.get("language") == "en")
    de_count = sum(1 for a in related_articles if a.get("language") == "de")
    if de_count > 0:
        print(f"      Language distribution: {en_count} EN, {de_count} DE")
    return related_articles


def cache_person(
    subject: str,
    *,
    person_id: Optional[str] = None,
    force: bool = False,
    max_related: int = 15,
    model: str = DEFAULT_MODEL,
) -> str:
    """Cache Wikipedia materials for a person."""
    # Find the Wikipedia page
    print(f"Looking up Wikipedia page for '{subject}'...")
    canonical_title = find_wikipedia_page(subject)
    print(f"Found page: '{canonical_title}'")

    # Determine person_id
    identifier = person_id or slugify(canonical_title)

    # Check if cache exists
    if not force and cache_exists(identifier):
        print(f"Cache already exists for '{identifier}'. Use --force to refresh.")
        return identifier

    # Fetch and cache materials
    ensure_cache(identifier, canonical_title, person_name=canonical_title)

    # Fetch and cache related articles by default
    if max_related > 0:
        try:
            related_articles = fetch_related_articles(
                canonical_title,
                max_related=max_related,
                model=model,
                use_cache=True,
                person_id=identifier,
            )
            if related_articles:
                cache_dir = get_cache_dir(identifier)
                related_path = cache_dir / "related_articles.json"
                related_path.write_text(
                    json.dumps(related_articles, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                print(f"  - Cached {len(related_articles)} related articles")
        except Exception as error:
            print(f"  - Warning: Failed to fetch related articles: {error}")

    # Fetch Deutsche Biographie data (best-effort, non-blocking)
    try:
        ensure_deutsche_biographie_cache(
            person_id=identifier,
            person_name=canonical_title,
        )
    except Exception as error:
        print(f"  - Warning: Deutsche Biographie fetch failed: {error}")

    return identifier


def parse_args(argv: Any) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Pre-fetch and cache Wikipedia materials for a person."
    )
    parser.add_argument(
        "subject", help="Person to cache materials for, e.g. 'Ada Lovelace' or 'henry_II'."
    )
    parser.add_argument(
        "--url",
        help="Wikipedia URL to use for disambiguation (e.g., 'https://en.wikipedia.org/wiki/Henry_II,_Holy_Roman_Emperor').",
    )
    parser.add_argument(
        "--id",
        dest="person_id",
        help="Optional person ID to use instead of auto-generating from title.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh cache even if it already exists.",
    )
    parser.add_argument(
        "--max-related",
        type=int,
        default=15,
        help="Maximum number of related articles to cache (default: 15, use 0 to disable).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            f"OpenAI model to use for AI ranking (default: {DEFAULT_MODEL}). "
            "Must support structured outputs."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Any = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # When URL is provided, use it for fetching but preserve original subject as person_id
    if args.url:
        subject_for_fetch = args.url
        # If --id is provided, use it; otherwise slugify the subject
        person_id_override = args.person_id or slugify(args.subject)
    else:
        subject_for_fetch = args.subject
        person_id_override = args.person_id

    try:
        person_id = cache_person(
            subject_for_fetch,
            person_id=person_id_override,
            force=args.force,
            max_related=args.max_related,
            model=args.model,
        )
        print(f"Successfully cached materials for '{person_id}'")
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
