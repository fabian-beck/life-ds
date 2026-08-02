#!/usr/bin/env python3
"""Check that the Wikipedia links in the generated data point at real articles.

Phase 2 of the person pipeline asks a model for the sources behind each event,
and the annotations it writes carry article links of their own. Both go straight
into ``life_events.json`` and are rendered as links the reader can follow, and
nothing has ever checked that they resolve. A model recalling an article title
that does not exist — or exists under a different name — is not a rare failure,
and a dead link is indistinguishable from a live one until someone clicks it.

Existence is cheap to establish: the MediaWiki API answers 50 titles per
request, follows redirects, and needs no key.

    python scripts/validate_source_links.py            # report
    python scripts/validate_source_links.py --check    # exit 1 on any dead link
    python scripts/validate_source_links.py --fix      # repair what search resolves

``--fix`` only rewrites a link when the site's own search returns a single
confident match for the title the model invented; anything else is reported for
a human, because guessing which article was meant is exactly the mistake being
corrected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
PEOPLE_DIR = REPO_ROOT / "data" / "people"
USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
BATCH_SIZE = 50
REQUEST_DELAY_SECONDS = 0.2


class WikipediaUnreachable(RuntimeError):
    """The API could not be asked, so nothing about the links is known."""


def _headers() -> Dict[str, str]:
    return {"User-Agent": USER_AGENT}


def parse_article(url: str) -> Optional[Tuple[str, str]]:
    """Split a wiki article URL into (language host, article title).

    Wikipedia and Wikisource both answer the same API at the same path, and the
    publication links carry Wikisource transcriptions, so both are checkable
    here. Returns None for anything else — the data also cites Deutsche
    Biographie, Commons file pages, DOIs, and museum sites, none of which this
    checker knows how to ask about.
    """
    parts = urlsplit(url)
    if not parts.netloc.endswith((".wikipedia.org", ".wikisource.org")):
        return None
    if not parts.path.startswith("/wiki/"):
        return None
    title = unquote(parts.path[len("/wiki/") :]).replace("_", " ").strip()
    if (
        not title
        or ":" in title.split(" ")[0]
        and title.split(":")[0]
        in {
            "File",
            "Category",
            "Special",
            "Help",
            "Template",
        }
    ):
        return None
    return parts.netloc, title


def collect_links(root: Path = PEOPLE_DIR) -> Dict[str, List[str]]:
    """Every Wikipedia URL in the data, mapped to the files that cite it."""
    citations: Dict[str, List[str]] = {}

    def note(url: Any, path: Path) -> None:
        if not isinstance(url, str) or not url:
            return
        where = path.relative_to(REPO_ROOT).as_posix()
        citations.setdefault(url, [])
        if where not in citations[url]:
            citations[url].append(where)

    for path in sorted(root.rglob("life_events.json")):
        if "_cache" in path.parts:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            for source in event.get("sources") or []:
                note(source, path)
            for annotation in (event.get("annotations") or {}).values():
                if isinstance(annotation, dict):
                    note(annotation.get("wikipedia_url"), path)
            event_class = event.get("event_class")
            if isinstance(event_class, dict):
                source_link = event_class.get("source_link")
                if isinstance(source_link, dict):
                    note(source_link.get("url"), path)
    return citations


def publication_link_urls(root: Path = PEOPLE_DIR) -> Set[str]:
    """The links that `enrich_publication_links.py` resolved and owns.

    A dead one is not repaired here. The link was written together with the
    entity it came from and the date it was resolved, and rewriting the URL
    alone would leave that provenance describing a different page; re-resolving
    the work is the repair.
    """
    urls: Set[str] = set()
    for path in sorted(root.rglob("life_events.json")):
        if "_cache" in path.parts:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            event_class = event.get("event_class")
            if not isinstance(event_class, dict):
                continue
            source_link = event_class.get("source_link")
            if isinstance(source_link, dict) and isinstance(
                source_link.get("url"), str
            ):
                urls.add(source_link["url"])
    return urls


def _batched(items: List[str], size: int) -> Iterable[List[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def existing_titles(host: str, titles: List[str]) -> Set[str]:
    """Ask one wiki which of these titles exist, following redirects.

    The answer is keyed by the title as asked, since a redirect renames it in
    the reply and the caller needs to recognize what it sent.
    """
    resolved: Set[str] = set()
    for batch in _batched(titles, BATCH_SIZE):
        try:
            response = requests.get(
                f"https://{host}/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "redirects": 1,
                    "titles": "|".join(batch),
                },
                headers=_headers(),
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise WikipediaUnreachable(f"{host}: {error}") from error

        query = payload.get("query") or {}
        # A redirect or a normalization renames the title in the reply, so each
        # asked title is followed forward to the page it lands on. Following the
        # rename backwards instead loses titles: when one cited title redirects
        # to another cited title, both arrive as one page, and only the redirect
        # would be credited — the direct citation would read as missing.
        renames: Dict[str, str] = {}
        for hop in (query.get("normalized") or []) + (query.get("redirects") or []):
            renames[hop.get("from", "")] = hop.get("to", "")

        def landing(name: str) -> str:
            seen = set()
            while name in renames and name not in seen:
                seen.add(name)
                name = renames[name]
            return name

        real_pages = {
            page.get("title", "")
            for page in (query.get("pages") or {}).values()
            if "missing" not in page
        }
        for title in batch:
            if landing(title) in real_pages:
                resolved.add(title)
        time.sleep(REQUEST_DELAY_SECONDS)
    return resolved


def _normalize(title: str) -> str:
    """A title reduced to its letters and digits, for comparing two spellings."""
    return "".join(char for char in title.casefold() if char.isalnum())


def _split(title: str) -> Tuple[List[str], Optional[str]]:
    """A title as (base words, trailing parenthetical disambiguator)."""
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", title)
    if match:
        return match.group(1).split(), match.group(2)
    return title.split(), None


def is_confident(requested: str, suggested: str) -> bool:
    """Whether a search result may be applied without a human looking.

    Search answers every query with something, and what it answers with is
    usually a different subject rather than a different spelling of the same
    one — "Stadtbaurat" returns "Zwickau", "Little Curies" returns "Marie
    Curie", and "George Washington's journey to the Ohio Country" returns the
    article about the man, which would silently broaden a citation about one
    week into one about a life. Only a result that reads as the same title
    respelled is accepted:

    - the same characters, differently spaced or capitalized
      ("Kunst Haus Wien" -> "KunstHausWien", "Maxxi" -> "MAXXI")
    - one trailing word dropped, neither side disambiguated
      ("Austrian Postal Savings Bank Building" -> "Austrian Postal Savings Bank")
    - the same subject, disambiguated differently but compatibly
      ("Samuel Seabury (Anglican bishop)" -> "Samuel Seabury",
       "Historicism (art and architecture)" -> "Historicism (art)")

    A disambiguator that merely *changes* is the case this refuses hardest:
    "Lawrence Washington (soldier)" and "Lawrence Washington (1659-1698)" are
    two different men.
    """
    if not _normalize(requested) or not _normalize(suggested):
        return False
    if _normalize(requested) == _normalize(suggested):
        return True

    asked_words, asked_paren = _split(requested)
    found_words, found_paren = _split(suggested)
    asked_base = [_normalize(word) for word in asked_words]
    found_base = [_normalize(word) for word in found_words]

    if asked_base != found_base:
        # A different base is only a respelling when it is this title minus a
        # trailing qualifier, and when no disambiguator is in play on either
        # side — those pick out *which* subject, not how it is spelled.
        if asked_paren or found_paren:
            return False
        return len(asked_base) - len(found_base) == 1 and asked_base[:-1] == found_base

    if found_paren is None:
        return True  # the request qualified a title that needs no qualifier
    if asked_paren is None:
        return False  # the article needs a qualifier the request never had
    asked_note, found_note = _normalize(asked_paren), _normalize(found_paren)
    return asked_note.startswith(found_note) or found_note.startswith(asked_note)


def search_replacement(host: str, title: str) -> Optional[str]:
    """The article a search for this title lands on, if any."""
    try:
        response = requests.get(
            f"https://{host}/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": title,
                "srlimit": 2,
            },
            headers=_headers(),
            timeout=30,
        )
        response.raise_for_status()
        results = (response.json().get("query") or {}).get("search") or []
    except Exception:
        return None
    time.sleep(REQUEST_DELAY_SECONDS)
    if not results:
        return None
    title_found = results[0].get("title")
    return str(title_found) if title_found else None


def article_url(host: str, title: str) -> str:
    return f"https://{host}/wiki/{title.replace(' ', '_')}"


def rewrite(citations: Dict[str, List[str]], replacements: Dict[str, str]) -> List[str]:
    """Apply URL replacements across every file that cites them."""
    touched: Set[str] = set()
    for url, files in citations.items():
        if url not in replacements:
            continue
        touched.update(files)

    changed: List[str] = []
    for relative in sorted(touched):
        path = REPO_ROOT / relative
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        for event in data.get("events") or []:
            if not isinstance(event, dict):
                continue
            sources = event.get("sources")
            if isinstance(sources, list):
                event["sources"] = [replacements.get(s, s) for s in sources]
            for annotation in (event.get("annotations") or {}).values():
                if isinstance(annotation, dict):
                    link = annotation.get("wikipedia_url")
                    if link in replacements:
                        annotation["wikipedia_url"] = replacements[link]
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        changed.append(relative)
    return changed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when any link is dead.",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite links that a search resolves to a single confident match.",
    )
    args = parser.parse_args(argv)

    citations = collect_links()
    by_host: Dict[str, Dict[str, List[str]]] = {}
    skipped = 0
    for url in citations:
        article = parse_article(url)
        if not article:
            skipped += 1
            continue
        host, title = article
        by_host.setdefault(host, {}).setdefault(title, []).append(url)

    total = sum(len(titles) for titles in by_host.values())
    print(
        f"{len(citations)} distinct link(s) cited; {total} Wikipedia article(s) "
        f"to check across {len(by_host)} wiki(s); {skipped} other host(s) skipped."
    )

    publication_links = publication_link_urls()
    dead: List[Tuple[str, str, str]] = []  # host, title, url
    for host, titles in sorted(by_host.items()):
        try:
            alive = existing_titles(host, sorted(titles))
        except WikipediaUnreachable as error:
            print(f"ERROR: could not reach {error}", file=sys.stderr)
            return 2
        for title in sorted(titles):
            if title not in alive:
                for url in titles[title]:
                    dead.append((host, title, url))

    if not dead:
        print("Every Wikipedia link resolves.")
        return 0

    print(f"\n{len(dead)} dead link(s):")
    replacements: Dict[str, str] = {}
    for host, title, url in dead:
        where = ", ".join(citations[url])
        print(f"  ✗ {url}\n      cited in {where}")
        if url in publication_links:
            print(
                "      publication link — re-resolve it with "
                "scripts/enrich_publication_links.py --force"
            )
            continue
        suggestion = search_replacement(host, title)
        if suggestion and suggestion != title and is_confident(title, suggestion):
            print(f"      resolves to: {suggestion}")
            replacements[url] = article_url(host, suggestion)
        elif suggestion:
            print(f"      search returns '{suggestion}' — too different to apply")
        else:
            print("      search returns nothing")

    if args.fix and replacements:
        changed = rewrite(citations, replacements)
        print(f"\nRewrote {len(replacements)} link(s) in {len(changed)} file(s):")
        for relative in changed:
            print(f"  {relative}")
        remaining = len(dead) - len(replacements)
        if remaining:
            print(f"{remaining} link(s) still need a human.")
        return 1 if remaining and args.check else 0

    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
