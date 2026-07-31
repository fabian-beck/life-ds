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

Entries are printed in IEEE form—initialed author block, title in quotation
marks, italicized journal or proceedings, `vol.`, `no.`, `pp.`, year, and the
DOI—with one departure: every author is named, where IEEE would cut a list of
more than six to `et al.` Numbering is positional—first citation gets `[1]`—so
the list at the end of the report is in the order a reader meets the works, and
inserting a citation renumbers everything after it without anyone editing a
number.

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
            return f"{format_names(self.fields['editor'])}, Eds."
        return ""

    def title(self) -> str:
        return self.fields.get("title", "")

    def segments(self) -> List[Tuple[str, str]]:
        """The entry as IEEE prints it, in runs of `(role, text)`.

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
            runs.append(("people", f"{people}, "))
        if self.title():
            runs.append(("title", f"{_quoted(self.title())} "))

        journal = self.fields.get("journal", "")
        booktitle = self.fields.get("booktitle", "")

        if journal:
            runs.append(("container", journal))
            locus = self._locus()
        elif booktitle:
            runs.append(("plain", "in "))
            runs.append(("container", booktitle))
            locus = self._locus(named=booktitle)
        else:
            # A book or a preprint: the work itself is what is italicized, and
            # it is the one case that names an imprint.
            if runs and runs[-1][0] == "title":
                runs[-1] = ("container", self.title())
            locus = self._locus(imprint=True)
        if locus:
            runs.append(("detail", f", {locus}, "))

        if self.url:
            # The identifier is the link; the closing period belongs to the
            # entry rather than to the address, so it stays outside it.
            runs.append(("plain", "doi: "))
            runs.append(("doi", self.doi))
            runs.append(("plain", "."))
        return runs

    def _locus(self, named: str = "", imprint: bool = False) -> str:
        """Volume, issue, pages and year—the part that says where to look.

        `named` is a container whose own title already carries the year, as a
        proceedings volume usually does. Printing it twice is what a BibTeX
        style does because it cannot read the title; here it can.
        """
        parts: List[str] = []
        volume = self.fields.get("volume", "")
        number = self.fields.get("number", "")
        year = self.fields.get("year", "")
        if volume:
            parts.append(f"vol. {volume}")
        if number:
            parts.append(f"no. {number}")
        if self.fields.get("articleno"):
            parts.append(f"Art. no. {self.fields['articleno']}")
        elif self.fields.get("pages"):
            parts.append(f"pp. {self.fields['pages'].replace('--', '–')}")
        if imprint and self.fields.get("publisher"):
            parts.append(self.fields["publisher"])
        if self.fields.get("note"):
            parts.append(self.fields["note"])
        if year and year not in named:
            parts.append(year)
        return ", ".join(parts)

    def describe(self) -> str:
        """The whole entry as plain text, for tooltips and error messages."""
        return "".join(text for _, text in self.segments()).strip()


def _quoted(title: str) -> str:
    """`Title` becomes `“Title,”`—the comma inside the closing quotation mark.

    A title that ends in its own terminal punctuation keeps it instead: `“Why
    Not?”` rather than `“Why Not?,”`.
    """
    if title.endswith(("?", "!")):
        return f"“{title}”"
    return f"“{title.rstrip('.')},”"


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
    """IEEE's author block: initials before the surname, and nobody cut.

    `Segel, Edward and Heer, Jeffrey` becomes `E. Segel and J. Heer`; three or
    more names take a serial comma, `A. Clauset, M. E. J. Newman, and C. Moore`.

    IEEE would abbreviate a list of more than six authors to the first name and
    `et al.` This one does not. A reference exists to name who did the work, and
    a list that hides seven of ten people saves a line and costs them the
    credit; the `.bib` entry keeps everyone either way, so the only thing the
    abbreviation would shorten is the page.
    """
    names = [
        part.strip()
        for part in re.split(r"\s+and\s+", raw)
        if part.strip() and part.strip().lower() != "others"
    ]
    formatted = [_initialed(name) for name in names]
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} and {formatted[1]}"
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


def _initialed(name: str) -> str:
    """`Henry Riche, Nathalie` becomes `N. Henry Riche`; initials stay initials.

    A compound surname survives because the `.bib` entry commits to it with a
    comma—`Henry Riche, Nathalie`—which is the one place that knowledge can be
    recorded. Guessing it back out of `Nathalie Henry Riche` is not possible.
    """
    family, given = _split_name(name)
    initials = " ".join(
        word if word.endswith(".") else f"{word[0]}." for word in given.split() if word
    )
    return f"{initials} {family}".strip()


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
