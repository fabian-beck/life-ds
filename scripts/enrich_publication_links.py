#!/usr/bin/env python3
"""Give every published work on a story slide a link the reader can follow.

A publication event carries a `event_class` block naming the work — its title,
its kind, sometimes its publisher — and the slide prints that name in a box of
its own. The name is where the reader's interest stops: the paper that made the
atom stable is right there on the screen, and there is nothing to click. The
event's own `sources` are about the *event* (the article the biography was
researched from), not about the work, so they cannot stand in for it.

This script resolves each work to one link and writes it into the data as
`event_class.source_link`. It asks, in order:

1. **Wikidata** — the open database. A work has an item there, and the item
   carries the links worth having: a Wikisource transcription, a full text at
   an institution, an Internet Archive scan, a DOI, an Open Library record, and
   the sitelinks of the encyclopedia articles about it. One item answers the
   question for every language at once, which is why it is asked first.
2. **Wikipedia** — the article *about the work*, when Wikidata is unreachable
   or has no item that survives the checks below. English first, then German,
   the two languages the app is written in.
3. **Nothing.** A work with no record anywhere gets no link, and the interface
   turns it into a search — built there rather than here, so it follows the
   reader's language and never goes stale in the data.

Which link a confirmed Wikidata item yields is a ranking, not a lookup:

    Wikisource → full-text URL → Internet Archive → Gutenberg
      → the encyclopedia article → DOI → Open Library → the item itself

The reader is on a biography slide, not in a library catalogue: a readable
transcription of the work beats an article about it, and an article about it
beats an identifier that resolves to a paywall. The DOI is kept below the
article for that reason alone — it is the more canonical record and the less
useful link.

**Nothing is written on a guess.** Search answers every query with something,
and for a work title what it answers with is usually a neighbouring subject:
"Das Rhenium" returns the article about the element, "Propaganda" the article
about the practice, "The Reynolds Pamphlet" a song from a musical. A candidate
is accepted only when its title *is* the work's title (a parenthetical
disambiguator aside — "Propaganda (book)" is the same title, and which subject
it names is exactly what the disambiguator settles) and the work's author is
named in the article's opening. The two checks are cheap and together they cut
the false matches the probe over this repository's own data produced.

    python scripts/enrich_publication_links.py --all
    python scripts/enrich_publication_links.py niels_bohr --verbose
    python scripts/enrich_publication_links.py --all --dry-run
    python scripts/enrich_publication_links.py --report        # no network
    python scripts/enrich_publication_links.py --all --force   # re-ask

Answers are cached in `data/_cache/publication_links.json`, negative ones
included, so a rerun costs nothing and a work that has no record is not looked
for again until `--force`. Links already in the data are kept unless `--force`
replaces them, which leaves a hand-corrected link alone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, unquote, urlsplit

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
PEOPLE_DIR = DATA_DIR / "people"
CACHE_PATH = Path(
    os.getenv(
        "LIFE_DS_PUBLICATION_LINK_CACHE",
        str(DATA_DIR / "_cache" / "publication_links.json"),
    )
)
USER_AGENT = "life-ds-data-generator/1.0 (+https://github.com/fabian-beck/life-ds)"
WIKIDATA_HOST = "www.wikidata.org"
# English first, then German: the app's two languages, and the order the
# interface would fall back in anyway.
ARTICLE_HOSTS = ("en.wikipedia.org", "de.wikipedia.org")
SITELINK_PREFERENCE = ("en", "de")
REQUEST_DELAY_SECONDS = 0.2
SEARCH_RESULTS = 5
LEAD_CHARACTERS = 700
# Characters a MediaWiki article path may carry unescaped.
ARTICLE_PATH_SAFE = "/:()',.!~*-_;+$@&="

# A parenthetical that says the article is about an adaptation rather than the
# work. "The Reynolds Pamphlet (song)" is a number from a musical, and its lead
# names the author of the pamphlet — the author check alone would let it in.
ADAPTATION_QUALIFIERS = {
    "album",
    "ballet",
    "film",
    "miniseries",
    "musical",
    "opera",
    "play",
    "podcast",
    "song",
    "tv series",
    "video game",
    "fernsehserie",
    "hörspiel",
    "lied",
    "oper",
    "theaterstück",
}


class SourceUnreachable(RuntimeError):
    """A service could not be asked, so it has said nothing about this work."""


@dataclass(frozen=True)
class Publication:
    """A published work as the data records it, with who wrote it."""

    person_id: str
    person_name: str
    person_article: Optional[str]
    title: str
    publication_type: Optional[str]
    event_index: int


@dataclass(frozen=True)
class SourceLink:
    """Where a work can be read, and what kind of place that is."""

    url: str
    kind: str
    site: str
    entity: Optional[str] = None
    resolved_by: str = "wikidata"

    def as_data(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "url": self.url,
            "kind": self.kind,
            "site": self.site,
        }
        if self.entity:
            record["entity"] = self.entity
        record["resolved_by"] = self.resolved_by
        record["resolved_on"] = date.today().isoformat()
        return record


# ---------------------------------------------------------------------------
# Titles: what counts as the same work
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """A title reduced to its letters and digits, for comparing two spellings."""
    return "".join(char for char in text.casefold() if char.isalnum())


def split_qualifier(title: str) -> Tuple[str, Optional[str]]:
    """A title as (base, trailing parenthetical), the parenthetical being what
    an encyclopedia adds to separate subjects that share a name."""
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", title)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return title.strip(), None


def title_variants(title: str) -> List[str]:
    """The forms of a title worth searching for.

    Generated titles carry glosses the catalogue does not — "Zahlbericht
    (report on algebraic number theory)", "Phänomenologie des Geistes
    (Phenomenology of Spirit)" — and both halves are worth asking about: the
    first is the work's name, the second is often its name in translation.
    """
    variants: List[str] = []

    def add(candidate: str) -> None:
        candidate = candidate.strip(" ,;:—–-")
        if candidate and candidate not in variants:
            variants.append(candidate)

    add(title)
    base, qualifier = split_qualifier(title)
    add(base)
    # A parenthetical is worth searching for only when it reads as a title of
    # its own. "(Vol. 1)" and "(1932)" locate a part of the work, not the work.
    if (
        qualifier
        and len(qualifier.split()) > 1
        and not any(char.isdigit() for char in qualifier)
    ):
        add(qualifier)
    return variants


def is_same_work(requested: str, candidate: str) -> bool:
    """Whether an article title names the work that was asked for.

    Deliberately stricter than the respelling test in
    `validate_source_links.py`, which repairs a link whose subject is known to
    be right. Here the subject is what is in doubt, and a title one word short
    of the work's is usually a different subject entirely: "Das Rhenium" is a
    book about the element "Rhenium". Only the disambiguator is ignored, since
    that is the encyclopedia's own addition and the author check decides
    whether it points at the work or at something named after it.
    """
    asked_base, _ = split_qualifier(requested)
    found_base, found_qualifier = split_qualifier(candidate)
    if found_qualifier and found_qualifier.casefold() in ADAPTATION_QUALIFIERS:
        return False
    if not normalize(asked_base):
        return False
    return normalize(asked_base) == normalize(found_base)


def author_names(person_name: str) -> List[str]:
    """The forms of an author's name an article's opening might use.

    The surname carries the check; the particles that precede it in German and
    Dutch names are dropped, because an article writes "Stauffenberg" where the
    registry writes "Claus von Stauffenberg".
    """
    parts = [part for part in re.split(r"\s+", person_name.strip()) if part]
    if not parts:
        return []
    names = {person_name.strip(), parts[-1]}
    if len(parts) > 2:
        names.add(" ".join(parts[-2:]))
    return [name for name in names if len(name) > 2]


def mentions_author(text: str, person_name: str) -> bool:
    lowered = text.casefold()
    return any(name.casefold() in lowered for name in author_names(person_name))


# ---------------------------------------------------------------------------
# MediaWiki and Wikidata
# ---------------------------------------------------------------------------


def _get(host: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = {"format": "json", "formatversion": "2", **params}
    try:
        response = requests.get(
            f"https://{host}/w/api.php",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as error:  # network, HTTP, or malformed JSON
        raise SourceUnreachable(f"{host}: {error}") from error
    time.sleep(REQUEST_DELAY_SECONDS)
    if not isinstance(payload, dict):
        raise SourceUnreachable(f"{host}: unexpected response")
    return payload


def search_articles(host: str, term: str, limit: int = SEARCH_RESULTS) -> List[str]:
    payload = _get(
        host,
        {"action": "query", "list": "search", "srsearch": term, "srlimit": limit},
    )
    results = (payload.get("query") or {}).get("search") or []
    return [str(item.get("title")) for item in results if item.get("title")]


def article_summary(host: str, title: str) -> Optional[Dict[str, Any]]:
    """An article's real title, its Wikidata item, and its opening text."""
    payload = _get(
        host,
        {
            "action": "query",
            "prop": "pageprops|extracts",
            "exintro": 1,
            "explaintext": 1,
            "redirects": 1,
            "titles": title,
        },
    )
    pages = (payload.get("query") or {}).get("pages") or []
    for page in pages:
        if page.get("missing"):
            return None
        props = page.get("pageprops") or {}
        return {
            "title": str(page.get("title") or title),
            "entity": props.get("wikibase_item"),
            "disambiguation": "disambiguation" in props,
            "lead": str(page.get("extract") or "")[:LEAD_CHARACTERS],
        }
    return None


def article_entity(article_url: Optional[str]) -> Optional[str]:
    """The Wikidata item behind an article URL, asked of the wiki itself.

    The person's item is needed to check a work's authorship, and the wiki that
    hosts the person's article can name it — which keeps the check working in
    environments that can reach Wikipedia but not Wikidata.
    """
    if not article_url:
        return None
    parts = urlsplit(article_url)
    if not parts.netloc.endswith(".wikipedia.org") or not parts.path.startswith(
        "/wiki/"
    ):
        return None
    title = unquote(parts.path[len("/wiki/") :]).replace("_", " ")
    try:
        summary = article_summary(parts.netloc, title)
    except SourceUnreachable:
        return None
    return summary.get("entity") if summary else None


def wikidata_search(title: str, limit: int = SEARCH_RESULTS) -> List[str]:
    """Item ids whose label or alias looks like this title, in any language."""
    payload = _get(
        WIKIDATA_HOST,
        {
            "action": "wbsearchentities",
            "search": title,
            "language": "en",
            "uselang": "en",
            "strictlanguage": 0,
            "type": "item",
            "limit": limit,
        },
    )
    return [str(hit.get("id")) for hit in payload.get("search") or [] if hit.get("id")]


def wikidata_entities(ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not ids:
        return {}
    payload = _get(
        WIKIDATA_HOST,
        {
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": "labels|aliases|claims|sitelinks/urls",
        },
    )
    entities = payload.get("entities") or {}
    return {key: value for key, value in entities.items() if isinstance(value, dict)}


def claim_values(entity: Dict[str, Any], prop: str) -> List[Any]:
    """The main values of one property, whatever their datatype."""
    values: List[Any] = []
    for claim in (entity.get("claims") or {}).get(prop) or []:
        snak = (claim or {}).get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        value = (snak.get("datavalue") or {}).get("value")
        if isinstance(value, dict):
            value = value.get("id") or value.get("text") or value
        if value is not None:
            values.append(value)
    return values


def entity_titles(entity: Dict[str, Any]) -> List[str]:
    """Every label and alias an item carries, in every language."""
    titles: List[str] = []
    for label in (entity.get("labels") or {}).values():
        if isinstance(label, dict) and label.get("value"):
            titles.append(str(label["value"]))
    for aliases in (entity.get("aliases") or {}).values():
        for alias in aliases or []:
            if isinstance(alias, dict) and alias.get("value"):
                titles.append(str(alias["value"]))
    return titles


def written_by(entity: Dict[str, Any], person_entity: Optional[str], name: str) -> bool:
    """Whether this item is a work of this person's.

    Two ways an item records authorship: `author` (P50) pointing at the
    person's item, and `author name string` (P2093) for authors without one.
    An item that records neither is not accepted — a title match on its own is
    what puts the wrong subject on the slide.
    """
    if person_entity and person_entity in claim_values(entity, "P50"):
        return True
    for value in claim_values(entity, "P2093"):
        if isinstance(value, str) and mentions_author(value, name):
            return True
    return False


# ---------------------------------------------------------------------------
# From a confirmed item to the one link
# ---------------------------------------------------------------------------

IDENTIFIER_LINKS: List[Tuple[str, str, str, Callable[[str], str]]] = [
    # property, kind, site, url builder
    ("P953", "full_text", "Full text", lambda value: value),
    (
        "P724",
        "internet_archive",
        "Internet Archive",
        lambda value: f"https://archive.org/details/{quote(value, safe='')}",
    ),
    (
        "P2034",
        "gutenberg",
        "Project Gutenberg",
        lambda value: f"https://www.gutenberg.org/ebooks/{quote(value, safe='')}",
    ),
]
LATE_IDENTIFIER_LINKS: List[Tuple[str, str, str, Callable[[str], str]]] = [
    ("P356", "doi", "DOI", lambda value: f"https://doi.org/{quote(value, safe='/')}"),
    (
        "P648",
        "open_library",
        "Open Library",
        lambda value: f"https://openlibrary.org/works/{quote(value, safe='')}",
    ),
]


def _sitelink(entity: Dict[str, Any], suffix: str) -> Optional[Tuple[str, str]]:
    """The preferred (language, url) sitelink of one project, if the item has one."""
    sitelinks = entity.get("sitelinks") or {}
    available: Dict[str, str] = {}
    for key, link in sitelinks.items():
        if not isinstance(link, dict) or not key.endswith(suffix):
            continue
        url = link.get("url")
        if url:
            available[key[: -len(suffix)]] = str(url)
    if not available:
        return None
    for language in SITELINK_PREFERENCE:
        if language in available:
            return language, available[language]
    language = sorted(available)[0]
    return language, available[language]


def _identifier_link(
    entity: Dict[str, Any],
    entity_id: str,
    table: Iterable[Tuple[str, str, str, Callable[[str], str]]],
) -> Optional[SourceLink]:
    for prop, kind, site, build in table:
        for value in claim_values(entity, prop):
            if isinstance(value, str) and value.strip():
                return SourceLink(build(value.strip()), kind, site, entity_id)
    return None


def choose_link(entity: Dict[str, Any], entity_id: str) -> SourceLink:
    """The best link an item offers, ranked for a reader rather than a catalogue."""
    transcription = _sitelink(entity, "wikisource")
    if transcription:
        return SourceLink(transcription[1], "wikisource", "Wikisource", entity_id)

    early = _identifier_link(entity, entity_id, IDENTIFIER_LINKS)
    if early:
        return early

    article = _sitelink(entity, "wiki")
    if article:
        return SourceLink(article[1], "wikipedia", "Wikipedia", entity_id)

    late = _identifier_link(entity, entity_id, LATE_IDENTIFIER_LINKS)
    if late:
        return late

    return SourceLink(
        f"https://www.wikidata.org/wiki/{entity_id}", "wikidata", "Wikidata", entity_id
    )


# ---------------------------------------------------------------------------
# The two resolvers
# ---------------------------------------------------------------------------


def resolve_via_wikidata(
    publication: Publication, person_entity: Optional[str], verbose: bool = False
) -> Optional[SourceLink]:
    """The open database's answer, or None when it has none that survives the checks."""
    for variant in title_variants(publication.title):
        ids = wikidata_search(variant)
        for entity_id, entity in wikidata_entities(ids).items():
            if not any(is_same_work(variant, title) for title in entity_titles(entity)):
                continue
            if not written_by(entity, person_entity, publication.person_name):
                if verbose:
                    print(f"      {entity_id}: title matches, authorship does not")
                continue
            return choose_link(entity, entity_id)
    return None


def article_queries(publication: Publication) -> List[Tuple[str, str]]:
    """The (search term, title to match against) pairs worth trying, in order.

    A work whose title is an ordinary word is not what a search for that word
    returns: "Propaganda" returns the practice, and Bernays's book — filed as
    "Propaganda (book)" — is nowhere in the first page of results. Adding the
    author's name to the *query* brings it to the top without loosening
    anything, since the answer is still checked against the work's title. The
    plain forms are asked first, so the extra query costs nothing when the
    title is distinctive.
    """
    queries: List[Tuple[str, str]] = []
    variants = title_variants(publication.title)
    for variant in variants:
        queries.append((variant, variant))
    surname = author_names(publication.person_name)
    if surname:
        for variant in variants:
            queries.append((f"{variant} {publication.person_name}", variant))
    seen: set[str] = set()
    unique: List[Tuple[str, str]] = []
    for term, expected in queries:
        if term not in seen:
            seen.add(term)
            unique.append((term, expected))
    return unique


def resolve_via_wikipedia(
    publication: Publication, person_entity: Optional[str], verbose: bool = False
) -> Optional[SourceLink]:
    """The encyclopedia article about the work, when one exists under its title."""
    for host in ARTICLE_HOSTS:
        for term, variant in article_queries(publication):
            for candidate in search_articles(host, term):
                if not is_same_work(variant, candidate):
                    continue
                summary = article_summary(host, candidate)
                if not summary or summary["disambiguation"]:
                    continue
                if person_entity and summary["entity"] == person_entity:
                    continue  # the author's own article, reached by their work
                if not is_same_work(variant, summary["title"]):
                    continue  # a redirect landed somewhere else
                if not mentions_author(summary["lead"], publication.person_name):
                    if verbose:
                        print(
                            f"      {host}: '{summary['title']}' does not name the author"
                        )
                    continue
                # Percent-encode what has to be, and nothing else: the links
                # already in the data leave parentheses and apostrophes as they
                # are, and only non-ASCII characters escaped.
                path = quote(summary["title"].replace(" ", "_"), safe=ARTICLE_PATH_SAFE)
                return SourceLink(
                    f"https://{host}/wiki/{path}",
                    "wikipedia",
                    "Wikipedia",
                    summary["entity"],
                    resolved_by="wikipedia",
                )
    return None


def resolve(
    publication: Publication,
    person_entity: Optional[str],
    unreachable: set[str],
    verbose: bool = False,
) -> Optional[SourceLink]:
    """Ask each source in turn; one being unreachable does not stop the others."""
    resolvers: List[Tuple[str, Callable[..., Optional[SourceLink]]]] = [
        ("wikidata", resolve_via_wikidata),
        ("wikipedia", resolve_via_wikipedia),
    ]
    for name, resolver in resolvers:
        if name in unreachable:
            continue
        try:
            link = resolver(publication, person_entity, verbose)
        except SourceUnreachable as error:
            unreachable.add(name)
            print(f"  ! {name} is unreachable ({error}); skipping it for this run")
            continue
        if link:
            return link
    return None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def cache_key(publication: Publication) -> str:
    return f"{publication.person_id}::{normalize(publication.title)}"


def load_cache() -> Dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Warning: ignoring unreadable publication link cache: {error}")
        return {}
    entries = payload.get("entries") if isinstance(payload, dict) else None
    return entries if isinstance(entries, dict) else {}


def save_cache(entries: Dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"version": 1, "entries": entries}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# The data
# ---------------------------------------------------------------------------


def person_files(person_id: str) -> List[Path]:
    """The English dataset and every translation of it.

    A link is not language-specific — the annotations in the data already cite
    English articles from the German documents — so every copy carries the same
    one, written here rather than waiting for a retranslation.
    """
    english = PEOPLE_DIR / person_id / "life_events.json"
    files = [english] if english.exists() else []
    for translated in sorted((PEOPLE_DIR / person_id).glob("*/life_events.json")):
        if "_cache" not in translated.parts:
            files.append(translated)
    return files


def publications_of(person_id: str) -> Tuple[List[Publication], Optional[str]]:
    """Every publication in a person's English dataset, and their article URL."""
    path = PEOPLE_DIR / person_id / "life_events.json"
    if not path.exists():
        return [], None
    data = json.loads(path.read_text(encoding="utf-8"))
    person = data.get("person") or {}
    name = str(person.get("name") or person_id).replace("_", " ")
    article = person.get("wikipedia")
    found: List[Publication] = []
    for index, event in enumerate(data.get("events") or []):
        if not isinstance(event, dict):
            continue
        event_class = event.get("event_class") or {}
        if event_class.get("type") != "publication":
            continue
        title = str(event_class.get("title") or "").strip()
        if not title:
            continue
        found.append(
            Publication(
                person_id=person_id,
                person_name=name,
                person_article=article if isinstance(article, str) else None,
                title=title,
                publication_type=event_class.get("publication_type"),
                event_index=index,
            )
        )
    return found, article if isinstance(article, str) else None


def write_links(
    person_id: str, links: Dict[int, Optional[Dict[str, Any]]], force: bool
) -> List[Path]:
    """Write the resolved links into every copy of a person's life events.

    Translations are index-aligned with the English document by construction,
    and `event_class` is copied verbatim into them rather than translated, so
    the title is checked as well before anything is written — a mismatch means
    the copies have drifted, and drifted data is not the place to guess.
    """
    changed: List[Path] = []
    for path in person_files(person_id):
        data = json.loads(path.read_text(encoding="utf-8"))
        events = data.get("events") or []
        touched = False
        for index, link in links.items():
            if link is None or index >= len(events):
                continue
            event_class = (events[index] or {}).get("event_class") or {}
            if event_class.get("type") != "publication":
                print(f"  ! {path.name}: event {index} is not a publication; skipped")
                continue
            if event_class.get("source_link") and not force:
                continue
            if event_class.get("source_link") == link:
                continue
            event_class["source_link"] = link
            touched = True
        if touched:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            changed.append(path)
    return changed


def enrich_events(
    events: List[Dict[str, Any]],
    person_name: str,
    person_article: Optional[str] = None,
    person_id: str = "",
    verbose: bool = False,
) -> int:
    """Resolve links for publications in an in-memory event list.

    This is the entry point the generation pipeline uses: the dataset is
    enriched before it is written, so a newly generated person arrives with the
    links already in place. It shares the cache with the standalone command, and
    it never raises — a work without a link is a normal outcome, and a service
    being unreachable is not a reason to fail a generation run.
    """
    cache = load_cache()
    person_entity = article_entity(person_article)
    unreachable: set[str] = set()
    resolved = 0
    for index, event in enumerate(events):
        event_class = (event or {}).get("event_class") or {}
        if event_class.get("type") != "publication" or event_class.get("source_link"):
            continue
        title = str(event_class.get("title") or "").strip()
        if not title:
            continue
        publication = Publication(
            person_id=person_id,
            person_name=person_name,
            person_article=person_article,
            title=title,
            publication_type=event_class.get("publication_type"),
            event_index=index,
        )
        key = cache_key(publication)
        if key in cache:
            record = cache[key]
        else:
            try:
                link = resolve(publication, person_entity, unreachable, verbose)
            except Exception as error:  # a link is never worth failing a run for
                print(f"  ! link lookup failed for '{title}': {error}")
                continue
            record = link.as_data() if link else None
            cache[key] = record
        if record:
            event_class["source_link"] = record
            resolved += 1
    save_cache(cache)
    return resolved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def all_person_ids() -> List[str]:
    return sorted(
        path.parent.name
        for path in PEOPLE_DIR.glob("*/life_events.json")
        if "_cache" not in path.parts
    )


def report(person_ids: Sequence[str]) -> int:
    """What the data holds right now, without asking anything of the network."""
    total = 0
    linked = 0
    by_kind: Dict[str, int] = {}
    missing: List[Tuple[str, str]] = []
    for person_id in person_ids:
        publications, _ = publications_of(person_id)
        path = PEOPLE_DIR / person_id / "life_events.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        events = data.get("events") or []
        for publication in publications:
            total += 1
            event_class = (events[publication.event_index] or {}).get(
                "event_class"
            ) or {}
            link = event_class.get("source_link")
            if link:
                linked += 1
                kind = str(link.get("kind") or "unknown")
                by_kind[kind] = by_kind.get(kind, 0) + 1
            else:
                missing.append((person_id, publication.title))
    print(f"{linked}/{total} publication(s) carry a source link.")
    for kind, count in sorted(by_kind.items(), key=lambda item: -item[1]):
        print(f"  {count:3d}  {kind}")
    if missing:
        print(f"\n{len(missing)} without one (the interface offers a search instead):")
        for person_id, title in missing:
            print(f"  {person_id}: {title}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("person_ids", nargs="*", help="Person ids to enrich.")
    parser.add_argument("--all", action="store_true", help="Every person in the data.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Resolve and print, write nothing."
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the links already in the data and stop (no network).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ask again for works already answered, and replace existing links.",
    )
    parser.add_argument("--verbose", action="store_true", help="Say what was rejected.")
    args = parser.parse_args(argv)

    person_ids = list(args.person_ids)
    if args.all or not person_ids:
        person_ids = all_person_ids()
    unknown = [pid for pid in person_ids if not (PEOPLE_DIR / pid).is_dir()]
    if unknown:
        print(f"Unknown person id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    if args.report:
        return report(person_ids)

    cache = load_cache()
    unreachable: set[str] = set()
    resolved_now = 0
    written_files = 0
    for person_id in person_ids:
        publications, article = publications_of(person_id)
        if not publications:
            continue
        print(f"\n{person_id}: {len(publications)} publication(s)")
        person_entity = article_entity(article)
        links: Dict[int, Optional[Dict[str, Any]]] = {}
        for publication in publications:
            key = cache_key(publication)
            if key in cache and not args.force:
                record = cache[key]
                state = "cached"
            else:
                link = resolve(publication, person_entity, unreachable, args.verbose)
                record = link.as_data() if link else None
                cache[key] = record
                state = "resolved"
                resolved_now += 1
            if record:
                print(f"  ✓ {publication.title}\n      {record['url']} ({state})")
                links[publication.event_index] = record
            else:
                print(f"  · {publication.title} — no record found ({state})")
        if not args.dry_run:
            changed = write_links(person_id, links, args.force)
            written_files += len(changed)

    if not args.dry_run:
        save_cache(cache)
        print(f"\nAsked about {resolved_now} work(s); wrote {written_files} file(s).")
    else:
        print(f"\nAsked about {resolved_now} work(s); wrote nothing (--dry-run).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
