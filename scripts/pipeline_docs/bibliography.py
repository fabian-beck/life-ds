#!/usr/bin/env python3
"""Read `docs/report/references.bib` and format it for the page.

The report cites literature the way it cites measurements: by key, resolved at
build time. `docs/report/references.bib` is the single place a work is
described, in ordinary BibTeX so an entry can be pasted into a paper unchanged,
and `[@key]` in the prose is checked against it exactly as `{{ fact }}` is
checked against `facts.py`.

Three rules make a reference an address rather than a gesture:

* Every entry carries a `doi`. A reference the reader cannot resolve names a
  work without saying where it is, and the DOI is the one identifier that stays
  valid when a publisher moves its pages.
* A citation with no entry fails the build, like an unknown fact.
* An entry nothing cites is reported as drift, like a measurement nobody quotes.

Entries are printed in Chicago's bibliography form—author block, title in
quotation marks, italicized journal or proceedings, volume and issue, condensed
page range, and the DOI as a resolvable URL—with every author named. Numbering
is positional—first citation gets `[1]`—so the list at the end of the report is
in the order a reader meets the works, and inserting a citation renumbers
everything after it without anyone editing a number.

None of that is an invitation to cite widely. The bibliography is meant to stay
small: a work belongs here when a sentence would otherwise have to argue a point
someone else has already settled, not when it is merely adjacent to the subject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BIB = REPO_ROOT / "docs" / "report" / "references.bib"

# The accents the bibliography actually uses, written as portable BibTeX and
# decoded once for the page. Kept deliberately short: an escape nobody wrote is
# not silently mangled, it simply never appears here.
ACCENTS = {
    ("v", "c"): "č",
    ("'", "c"): "ć",
    ("'", "e"): "é",
    ('"', "o"): "ö",
    ("'", "o"): "ó",
    ('"', "u"): "ü",
    ('"', "a"): "ä",
    ("'", "a"): "á",
    ("`", "e"): "è",
    ("^", "e"): "ê",
    ("~", "n"): "ñ",
}

ACCENT = re.compile(
    r"\{\\(['\"`^~v])\s*\{?([A-Za-z])\}?\}|\\(['\"`^~v])\s*\{([A-Za-z])\}"
)
ENTRY_START = re.compile(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,")


class BibliographyError(ValueError):
    """A fault in the `.bib` file, reported with enough to find it."""


@dataclass(frozen=True)
class Reference:
    """One work, as the page prints it."""

    key: str
    kind: str
    fields: Dict[str, str]

    @property
    def doi(self) -> str:
        return self.fields.get("doi", "")

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else ""

    def people(self) -> str:
        """The author list, or the editors of an edited volume."""
        if self.fields.get("author"):
            return format_names(self.fields["author"])
        if self.fields.get("editor"):
            return f"{format_names(self.fields['editor'])}, eds."
        return ""

    def title(self) -> str:
        return self.fields.get("title", "")

    def segments(self) -> List[Tuple[str, str]]:
        """The entry as Chicago prints it, in runs of `(role, text)`.

        Each run carries its own punctuation and spacing, so the page and the
        plain text are assembled by concatenation and cannot disagree: what a
        citation's tooltip says is character for character what the reference
        list prints. `container` is the run the stylesheet italicizes—the
        journal or the proceedings—and `title` is the one it puts in quotation
        marks, which is the distinction the style rests on.
        """
        runs: List[Tuple[str, str]] = []
        people = self.people()
        if people:
            runs.append(("people", f"{_close(people)} "))
        if self.title():
            runs.append(("title", f"“{_close(self.title())}” "))

        journal = self.fields.get("journal", "")
        booktitle = self.fields.get("booktitle", "")
        year = self.fields.get("year", "")
        located = _located(self.fields)

        if journal:
            runs.append(("container", journal))
            detail = _volume(self.fields)
            if year:
                detail += f" ({year})"
            detail += f": {located}." if located else "."
            runs.append(("detail", f"{detail} "))
        elif booktitle:
            runs.append(("plain", "In "))
            runs.append(("container", booktitle))
            tail = f", {located}." if located else "."
            imprint = ", ".join(
                part for part in (self.fields.get("publisher", ""), year) if part
            )
            runs.append(("detail", f"{tail} {imprint}. " if imprint else f"{tail} "))
        else:
            # A book or a preprint: the title itself is the italicized work.
            if runs and runs[-1][0] == "title":
                runs[-1] = ("container", f"{_close(self.title())} ")
            imprint = ", ".join(
                part
                for part in (
                    self.fields.get("publisher", ""),
                    self.fields.get("note", ""),
                    year,
                )
                if part
            )
            if imprint:
                runs.append(("detail", f"{imprint}. "))

        if self.url:
            # The closing period belongs to the entry, not to the address, so it
            # is a run of its own and stays outside the link.
            runs.append(("doi", self.url))
            runs.append(("plain", "."))
        return runs

    def describe(self) -> str:
        """The whole entry as plain text, for tooltips and error messages."""
        return "".join(text for _, text in self.segments()).strip()


def _close(text: str) -> str:
    """Close a run with a period, unless it already ends in one."""
    return text if text.endswith((".", "?", "!")) else f"{text}."


def _volume(fields: Dict[str, str]) -> str:
    volume = fields.get("volume", "")
    number = fields.get("number", "")
    if volume and number:
        return f" {volume}, no. {number}"
    return f" {volume}" if volume else ""


def _located(fields: Dict[str, str]) -> str:
    """Where in the volume: an article number, or a condensed page range."""
    if fields.get("articleno"):
        return fields["articleno"]
    return condense_pages(fields.get("pages", ""))


def condense_pages(pages: str) -> str:
    """Abbreviate an inclusive page range the way Chicago does.

    1139--1148 prints as 1139–48, 156--160 as 156–60, but 31--38 keeps both
    numbers. The rule (CMOS 9.61) turns on the first number: below 100 or an
    exact multiple of 100 it is spelled out in full; ending 01 through 09 it
    drops to whatever digits changed; otherwise it keeps two digits, or more
    when two would not carry the reader across the hundred.
    """
    parts = [part for part in re.split(r"-+|–", pages) if part]
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return pages.replace("--", "–")
    first, second = parts
    start = int(first)
    if start < 100 or start % 100 == 0 or len(first) != len(second):
        return f"{first}–{second}"
    shared = 0
    while shared < len(first) and first[shared] == second[shared]:
        shared += 1
    changed = second[shared:] or second[-1:]
    if start % 100 >= 10 and len(changed) < 2:
        changed = second[-2:]
    return f"{first}–{changed}"


@dataclass(frozen=True)
class Bibliography:
    """Every declared work, keyed as the prose cites it."""

    entries: Dict[str, Reference]
    path: str = DEFAULT_BIB.name

    def get(self, key: str) -> Optional[Reference]:
        return self.entries.get(key)

    def keys(self) -> List[str]:
        return list(self.entries)

    def __len__(self) -> int:
        return len(self.entries)


def decode(value: str) -> str:
    """Turn BibTeX's accents and grouping braces into the text to display."""

    def accent(match: re.Match) -> str:
        mark = match.group(1) or match.group(3)
        letter = match.group(2) or match.group(4)
        replacement = ACCENTS.get((mark, letter))
        if replacement is None:
            raise BibliographyError(
                f"unsupported accent '{match.group(0)}'—add it to "
                "bibliography.ACCENTS or write the letter directly"
            )
        return replacement

    decoded = ACCENT.sub(accent, value)
    return " ".join(decoded.replace("{", "").replace("}", "").split())


def format_names(raw: str) -> str:
    """Chicago's author block: everyone, first one inverted, nobody cut.

    `Segel, Edward and Heer, Jeffrey` becomes `Segel, Edward, and Jeffrey
    Heer`. Only the leading name is inverted, because inversion exists to put
    the alphabetizing surname first and the rest of the list is read, not
    sorted. Given names are printed as the work prints them—full where the work
    gives them in full, initials where it does not.

    Nothing is abbreviated to `et al.`: a bibliography that hides seven of ten
    authors makes the contribution of seven people unsearchable, and the space
    it saves is a line.
    """
    names = [
        part.strip()
        for part in re.split(r"\s+and\s+", raw)
        if part.strip() and part.strip().lower() != "others"
    ]
    if not names:
        return ""
    formatted = [_inverted(names[0])] + [_natural(name) for name in names[1:]]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]}, and {formatted[1]}"
    return ", ".join(formatted[:-1]) + f", and {formatted[-1]}"


def _split_name(name: str) -> Tuple[str, str]:
    """`Henry Riche, Nathalie` and `Nathalie Henry Riche` both split the same."""
    if "," in name:
        family, _, given = name.partition(",")
        return family.strip(), given.strip()
    words = name.split()
    if not words:
        return name, ""
    return words[-1], " ".join(words[:-1])


def _inverted(name: str) -> str:
    family, given = _split_name(name)
    return f"{family}, {given}" if given else family


def _natural(name: str) -> str:
    family, given = _split_name(name)
    return f"{given} {family}" if given else family


def parse(text: str, path: str = DEFAULT_BIB.name) -> Bibliography:
    """Read BibTeX entries. Comments, `@string` and stray text are skipped."""
    entries: Dict[str, Reference] = {}
    for match in ENTRY_START.finditer(text):
        kind = match.group(1).lower()
        key = match.group(2)
        if kind in ("string", "comment", "preamble"):
            continue
        body, end = _entry_body(text, match.end())
        if end < 0:
            raise BibliographyError(f"{path}: entry '{key}' is never closed with '}}'")
        if key in entries:
            raise BibliographyError(f"{path}: '{key}' is defined twice")
        entries[key] = Reference(key, kind, _fields(body, key, path))
    if not entries:
        raise BibliographyError(f"{path}: no BibTeX entries found")
    return Bibliography(entries, path)


def _entry_body(text: str, start: int) -> Tuple[str, int]:
    depth = 1
    cursor = start
    while cursor < len(text):
        char = text[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:cursor], cursor
        cursor += 1
    return "", -1


def _fields(body: str, key: str, path: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    cursor = 0
    while cursor < len(body):
        match = re.compile(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*").search(body, cursor)
        if match is None:
            break
        name = match.group(1).lower()
        value, cursor = _value(body, match.end(), key, path)
        fields[name] = decode(value)
    if not fields.get("title"):
        raise BibliographyError(f"{path}: '{key}' has no title")
    return fields


def _value(body: str, start: int, key: str, path: str) -> Tuple[str, int]:
    if body[start] == "{":
        depth = 0
        cursor = start
        while cursor < len(body):
            if body[cursor] == "{":
                depth += 1
            elif body[cursor] == "}":
                depth -= 1
                if depth == 0:
                    return body[start + 1 : cursor], cursor + 1
            cursor += 1
        raise BibliographyError(f"{path}: a value of '{key}' is never closed")
    if body[start] == '"':
        end = body.find('"', start + 1)
        if end < 0:
            raise BibliographyError(f"{path}: a value of '{key}' is never closed")
        return body[start + 1 : end], end + 1
    end = body.find(",", start)
    end = len(body) if end < 0 else end
    return body[start:end].strip(), end + 1


_cache: Dict[Path, Bibliography] = {}


def load(path: Optional[Path] = None) -> Bibliography:
    """Parse a `.bib` file, once per path."""
    where = Path(path) if path else DEFAULT_BIB
    if where not in _cache:
        if not where.is_file():
            raise BibliographyError(f"no bibliography at {where}")
        _cache[where] = parse(
            where.read_text(encoding="utf-8"),
            where.name,
        )
    return _cache[where]


def default() -> Bibliography:
    """The report's own bibliography, or an empty one if it is missing."""
    try:
        return load()
    except BibliographyError:
        return Bibliography({})


def check(bibliography: Bibliography, cited: Sequence[str]) -> List[Tuple[str, str]]:
    """Faults in the bibliography as a whole, as `(severity, message)` pairs.

    A citation with no entry is caught in the compiler, where the line number
    is. What is left is the file's own health—an entry that cannot be resolved,
    and an entry the report never uses.
    """
    problems: List[Tuple[str, str]] = []
    for key, entry in bibliography.entries.items():
        if not entry.doi:
            problems.append(
                (
                    "error",
                    f"reference '{key}' has no doi—every entry has to be "
                    "resolvable, so add one or drop the entry",
                )
            )
        if not entry.people():
            problems.append(
                ("error", f"reference '{key}' has neither an author nor an editor")
            )
        if not entry.fields.get("year"):
            problems.append(("error", f"reference '{key}' has no year"))
    for key in sorted(set(bibliography.keys()) - set(cited)):
        problems.append(("warning", f"reference '{key}' is declared but never cited"))
    return problems
