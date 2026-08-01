#!/usr/bin/env python3
"""Compile the authored Markdown report into the page's body.

The report has two kinds of content and they are kept strictly apart.

*Authored* material—motivation, design rationale, the reasons a step exists at
all—lives in `docs/report/report.md`, written by hand, because no amount of
static analysis can explain why a decision was made. *Computed*
material—counts, models, prompts, schemas, the dependency graphs—is
never written down in the markdown. The markdown only says where it goes, and
this module leaves a mount point that the page fills from the build payload. A
rebuild therefore refreshes every number and every figure without anyone editing
a sentence, and a sentence can never contradict the code.

The authoring surface is small on purpose:

`## Heading` / `### Heading`
    Sections and subsections. Numbering, ids and the table of contents are
    derived, so reordering a section renumbers the report.

`{{ some.fact }}`
    A citable measurement from `facts.py`, rendered with its provenance as a
    tooltip. An unknown key fails the build rather than printing
    nothing—a hole in a sentence is worse than a broken build.

`[[part|phrase]]` / `[[part]]`
    A reference from a phrase into a named part of the teaser figure. The id is
    resolved against `teaser.PARTS`, so a reference into the figure is checked
    the same way a number is: the phrase reads as ordinary prose, and the page
    turns it into a two-way link between the sentence and the drawing. Where
    the part carries one of the system's concepts, the phrase is marked with
    that concept's glyph—the same glyph the figures and the interface use—so a
    reader meets the vocabulary in the sentence that introduces it.

`[@key]` / `[@key; @other]`
    A citation of published work, resolved against `docs/report/references.bib`
    the same way a fact is resolved against `facts.py`. Numbering follows first
    use, and `::: references` prints the list the numbers point into.

`::: component key=value`
    A mount point for computed content. The block's own body is authored prose
    that introduces the component and is kept above it.

`::: note` / `::: aside` / `::: decision` / `::: limitation`
    Callouts rendered here in Python; they hold authored text only.

`::: principles`
    The design principles, declared once as `@id Title` lines with a paragraph
    under each. Numbering is positional, so reordering the block renumbers
    every reference to it.

`((id))`
    A reference to one of those principles, rendered as its number. The prose
    argues a decision where the system acts on it and points at the principle
    it instantiates instead of restating it; the page opens the principle in a
    popover, and on paper the number resolves against the printed list.

`^[an explanation]`
    An inline note: an aside a specialist reader may want and the sentence
    cannot carry. One authored source, two renderings—a numbered note at the
    end of its section on paper, a popover on the marker on screen.

Anything else is ordinary Markdown, rendered by `markdown` with tables,
footnotes, definition lists and fenced code enabled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import markdown

from . import bibliography, concepts, teaser
from .bibliography import Bibliography, Reference
from .facts import Fact

MARKDOWN_EXTENSIONS = [
    "tables",
    "fenced_code",
    "footnotes",
    "def_list",
    "attr_list",
    "sane_lists",
    "smarty",
]

MARKDOWN_CONFIGS = {
    "footnotes": {"BACKLINK_TEXT": "&#8617;"},
    "smarty": {"smart_dashes": True, "smart_quotes": True},
}


# ---------------------------------------------------------------------------
# The component roster
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentSpec:
    """A computed block the markdown may mount, and what it needs to be valid.

    `figures` and `tables` are how many numbered captions the component emits,
    which is what lets numbering be assigned here—in document order, in
    Python, where it can be tested—instead of counted at runtime.
    """

    name: str
    summary: str
    required: Tuple[str, ...] = ()
    optional: Tuple[str, ...] = ()
    figures: int = 0
    tables: int = 0


COMPONENTS: Dict[str, ComponentSpec] = {
    spec.name: spec
    for spec in [
        ComponentSpec(
            "buildinfo",
            "Commit, branch and build time of this rendering.",
        ),
        ComponentSpec(
            "teaser",
            "The whole system on one canvas, in parts the prose can point at.",
            figures=1,
        ),
        ComponentSpec(
            "factgrid",
            "A labeled grid of measurements, each with its source.",
            required=("keys",),
            optional=("caption",),
        ),
        ComponentSpec(
            "pipeline",
            "One pipeline as an interactive layered dependency graph.",
            required=("lane",),
            figures=1,
        ),
        ComponentSpec(
            "steptable",
            "Every documented step of one pipeline, with model and schema.",
            required=("lane",),
            tables=1,
        ),
        ComponentSpec(
            "conceptlegend",
            "What the system reads and what it derives, with the glyph for each.",
        ),
        ComponentSpec(
            "modeltable",
            "Each model call site, its model and its reasoning effort.",
            tables=1,
        ),
        ComponentSpec(
            "cliflags",
            "The command-line options of one script, from its argument parser.",
            required=("script",),
            tables=1,
        ),
        ComponentSpec(
            "schemalist",
            "Structured-output schemas, expanded field by field.",
            optional=("names",),
        ),
        ComponentSpec(
            "screenshot",
            "A view of the running application, captured from a described position.",
            required=("id", "route", "caption"),
            optional=(
                "width",
                "height",
                "scale",
                "clip",
                "wait",
                "anchor",
                "settle",
                "scroll",
                "format",
                "quality",
                "alt",
            ),
            figures=1,
        ),
        ComponentSpec(
            "kindlegend",
            "What the four step-kind colors mean.",
        ),
        ComponentSpec(
            "coverage",
            "Which model call sites the spec claims, and any it does not.",
        ),
    ]
}

CALLOUTS: Dict[str, str] = {
    "note": "Note",
    "aside": "Aside",
    "decision": "Design decisions",
    "limitation": "Limitation",
}

DIRECTIVE_OPEN = re.compile(r"^:::\s*([a-z][a-z0-9_-]*)\s*(.*)$")
DIRECTIVE_CLOSE = re.compile(r"^:::\s*$")
HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
CITATION = re.compile(r"(?<!\\)\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")
FIGREF = re.compile(r"(?<!\\)\[\[\s*([a-z][a-z0-9-]*)\s*(?:\|\s*([^\]]+?)\s*)?\]\]")
PRINCIPLE_REF = re.compile(r"(?<!\\)\(\(\s*([a-z][a-z0-9-]*)\s*\)\)")
PRINCIPLE_ITEM = re.compile(r"^@([a-z][a-z0-9-]*)\s+(\S.*?)\s*$")
PRINCIPLES_BLOCK = "principles"
KEY = r"[A-Za-z][A-Za-z0-9_:.-]*"
REFCITE = re.compile(rf"(?<!\\)\[@\s*({KEY}(?:\s*[;,]\s*@\s*{KEY})*)\s*\]")
PARAM = re.compile(r"""([a-z][a-z0-9_-]*)=(?:"([^"]*)"|'([^']*)'|(\S+))""")
FENCE = re.compile(r"^\s*(```|~~~)")
ORCID_ID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """A numbered heading, for the table of contents and the sticky nav."""

    number: str
    level: int
    title: str
    slug: str
    children: List["Section"] = field(default_factory=list)

    def to_json(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "level": self.level,
            "title": self.title,
            "slug": self.slug,
            "children": [child.to_json() for child in self.children],
        }


@dataclass
class Mount:
    """A resolved `::: component` block, ready to be hydrated by the page."""

    component: str
    params: Dict[str, str]
    body_markdown: str
    figure_start: int
    table_start: int
    line: int


@dataclass
class Note:
    """One inline note, numbered in document order.

    The marker carries no text: both renderings read the same authored body,
    which is emitted once as list item `note-{number}` at the end of the note's
    section.
    """

    number: int
    body_markdown: str
    body_html: str


@dataclass
class Author:
    """One author of the report, as the title block prints them.

    Written in the front matter as `Name | Affiliation | page | ORCID`, of which
    only the name is required: a contributor without a public page or without an
    ORCID iD still belongs on the title block, and the renderer prints whichever
    of the four fields the line supplied.
    """

    name: str
    affiliation: str = ""
    url: str = ""
    orcid: str = ""

    @property
    def orcid_url(self) -> str:
        return f"https://orcid.org/{self.orcid}" if self.orcid else ""

    def to_json(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "affiliation": self.affiliation,
            "url": self.url,
            "orcid": self.orcid,
        }


@dataclass
class Principle:
    """One numbered design principle, declared once and referenced anywhere.

    The number is the reference: prose writes `((id))` and reads `P3`, so a
    principle can be pointed at from the section that acts on it without the
    sentence having to restate it. Numbering is positional, like the headings
    and the reference list, so nobody maintains a number by hand.
    """

    number: int
    id: str
    title: str
    body_markdown: str
    title_html: str = ""
    body_html: str = ""

    @property
    def label(self) -> str:
        return f"P{self.number}"

    def to_json(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "id": self.id,
            "label": self.label,
            "title": self.title,
        }


@dataclass
class Document:
    front: Dict[str, str]
    html: str
    sections: List[Section]
    mounts: List[Mount]
    citations: List[str]
    source_path: str
    figrefs: List[str] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)
    refcites: List[str] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    prints_references: bool = False
    principles: List[Principle] = field(default_factory=list)
    prefs: List[str] = field(default_factory=list)
    authors: List[Author] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.front.get("title", "Technical report")

    def to_json(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.front.get("subtitle", ""),
            "authors": [author.to_json() for author in self.authors],
            "abstract": self.front.get("abstract", ""),
            "source": self.source_path,
            "sections": [section.to_json() for section in self.sections],
            "principles": [item.to_json() for item in self.principles],
            "components": {
                name: {"summary": spec.summary} for name, spec in COMPONENTS.items()
            },
        }


@dataclass
class Block:
    kind: str  # "markdown" | "component" | "callout"
    text: str
    name: str = ""
    params: Dict[str, str] = field(default_factory=dict)
    line: int = 0


class ReportError(ValueError):
    """A fault in the authored source, reported with its line number."""


def split_front_matter(text: str) -> Tuple[Dict[str, str], str, int]:
    """`---` fenced `key: value` header. A blank value opens an indented block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 0

    front: Dict[str, str] = {}
    key: Optional[str] = None
    buffer: List[str] = []
    for index, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            if key is not None:
                front[key] = "\n".join(buffer).strip()
            return front, "\n".join(lines[index:]), index
        if line[:1].isspace() and key is not None:
            buffer.append(line.strip())
            continue
        if ":" not in line:
            if not line.strip():
                continue
            raise ReportError(f"line {index}: front matter expects 'key: value'")
        if key is not None:
            front[key] = "\n".join(buffer).strip()
        name, _, value = line.partition(":")
        key = name.strip()
        buffer = [value.strip()] if value.strip() else []
    raise ReportError("front matter is not closed with '---'")


def parse_authors(text: str) -> List[Author]:
    """One author per line of the `authors:` block, fields separated by `|`.

    `Name | Affiliation | page | ORCID`, trailing fields optional. The ORCID iD
    may be written bare or as its `https://orcid.org/...` form—both are stored
    bare and linked by the renderer—and its checksum shape is verified here so a
    mistyped iD fails the build rather than pointing a reader at a stranger.
    """
    authors: List[Author] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = [part.strip() for part in line.split("|")]
        if len(fields) > 4:
            raise ReportError(
                f"author {fields[0]!r}: expected 'Name | Affiliation | page | "
                "ORCID', with the last three optional"
            )
        fields += [""] * (4 - len(fields))
        name, affiliation, url, orcid = fields
        if not name:
            raise ReportError("an author line must start with a name")
        orcid = orcid.rstrip("/").rsplit("/", 1)[-1]
        if orcid and not ORCID_ID.fullmatch(orcid):
            raise ReportError(
                f"author {name!r}: {orcid!r} is not an ORCID iD "
                "(0000-0000-0000-0000)"
            )
        authors.append(Author(name, affiliation, url, orcid))
    return authors


def parse_params(text: str, line: int) -> Dict[str, str]:
    params: Dict[str, str] = {}
    remainder = text.strip()
    for match in PARAM.finditer(remainder):
        value = next(group for group in match.groups()[1:] if group is not None)
        params[match.group(1)] = value
        remainder = remainder.replace(match.group(0), "", 1)
    if remainder.strip():
        raise ReportError(
            f"line {line}: could not read directive arguments {remainder.strip()!r}"
            '—use key=value or key="two words"'
        )
    return params


def split_blocks(body: str, offset: int) -> List[Block]:
    """Cut the body into prose and directives, honoring code fences."""
    blocks: List[Block] = []
    prose: List[str] = []
    fence: Optional[str] = None
    open_block: Optional[Block] = None
    nested: List[str] = []

    def flush_prose() -> None:
        if any(line.strip() for line in prose):
            blocks.append(Block("markdown", "\n".join(prose)))
        prose.clear()

    for index, line in enumerate(body.splitlines(), start=offset + 1):
        fence_match = FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            (nested if open_block else prose).append(line)
            continue
        if fence is not None:
            (nested if open_block else prose).append(line)
            continue

        if open_block is not None:
            if DIRECTIVE_CLOSE.match(line):
                open_block.text = "\n".join(nested).strip("\n")
                blocks.append(open_block)
                open_block = None
                nested = []
            else:
                nested.append(line)
            continue

        opened = DIRECTIVE_OPEN.match(line)
        if opened and not DIRECTIVE_CLOSE.match(line):
            name = opened.group(1)
            kind = "callout" if name in CALLOUTS else "component"
            flush_prose()
            open_block = Block(
                kind,
                "",
                name=name,
                params=parse_params(opened.group(2), index),
                line=index,
            )
            nested = []
            continue

        prose.append(line)

    if open_block is not None:
        raise ReportError(
            f"line {open_block.line}: '::: {open_block.name}' is never closed with ':::'"
        )
    if fence is not None:
        raise ReportError("a fenced code block is never closed")
    flush_prose()
    return blocks


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _slug(title: str, used: Dict[str, int]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    used[base] = used.get(base, 0) + 1
    return base if used[base] == 1 else f"{base}-{used[base]}"


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _outside_fences(text: str, replace: Callable[[str], str]) -> str:
    """Apply an inline rewrite to prose only.

    A fenced block is the one place the report can show its own syntax, so
    nothing inside one is ever substituted.
    """
    out: List[str] = []
    fence: Optional[str] = None
    for raw in text.splitlines():
        fence_match = FENCE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            fence = None if fence == marker else (fence or marker)
            out.append(raw)
            continue
        out.append(raw if fence else replace(raw))
    return "\n".join(out)


def substitute_citations(
    text: str, facts: Dict[str, Fact], seen: List[str], line_hint: str = ""
) -> str:
    """Replace `{{ key }}` with the measurement and its provenance."""

    def replace(match: re.Match) -> str:
        key = match.group(1)
        seen.append(key)
        fact = facts.get(key)
        if fact is None:
            raise ReportError(
                f"{line_hint}unknown fact '{{{{ {key} }}}}'—add it to "
                "pipeline_docs/facts.py or fix the citation"
            )
        return (
            f'<span class="cite" title="{_escape(fact.source)}" '
            f'data-fact="{_escape(key)}">{_escape(fact.display)}</span>'
        )

    substituted = _outside_fences(text, lambda line: CITATION.sub(replace, line))
    return substituted.replace("\\{{", "{{")


def concept_glyph(concept_id: str, cls: str = "glyph") -> str:
    """A concept's icon as inline SVG, or nothing at all.

    Inline rather than a sprite or a font: the report is one self-contained
    file that has to render from `file://`, and a mark that fails to load is
    worse than a mark that was never drawn.
    """
    path = concepts.icon_of(concept_id)
    if not path:
        return ""
    return (
        f'<svg class="{_escape(cls)}" viewBox="0 0 24 24" aria-hidden="true" '
        f'focusable="false"><path d="{_escape(path)}"/></svg>'
    )


def substitute_figrefs(text: str, seen: List[str], line_hint: str = "") -> str:
    """Replace `[[part|phrase]]` with a control that points into the figure.

    The phrase stays ordinary prose—the sentence has to read the same with the
    figure, without it, and on paper—so the element carries the relation and
    nothing else. Resolving the id here rather than in the page is what makes a
    reference into the figure a build-time claim: a part that was renamed or
    removed stops the build instead of leaving a phrase that lights nothing.

    A part that carries a concept contributes its glyph, drawn ahead of the
    phrase and hidden from assistive technology, since the words already say
    what the mark repeats. The glyph is the one the application draws for the
    same thing, which is what lets a reader carry the vocabulary from a
    sentence into a figure and from a figure into the product.
    """

    def replace(match: re.Match) -> str:
        part_id = match.group(1)
        phrase = match.group(2)
        part = teaser.part_by_id(part_id)
        if part is None:
            raise ReportError(
                f"{line_hint}unknown figure part '[[{part_id}]]'—the teaser "
                "draws " + ", ".join(teaser.part_ids())
            )
        seen.append(part_id)
        label = phrase if phrase else part.label
        return (
            f'<button type="button" class="figref" data-part="{_escape(part_id)}" '
            f'aria-label="{_escape(label)}—show '
            f'{_escape(part.label)} in the figure">'
            f"{concept_glyph(part.concept)}{_escape(label)}</button>"
        )

    substituted = _outside_fences(text, lambda line: FIGREF.sub(replace, line))
    return substituted.replace("\\[[", "[[")


# ---------------------------------------------------------------------------
# Design principles
# ---------------------------------------------------------------------------


def parse_principles(text: str, line_hint: str = "") -> List[Principle]:
    """Read a `::: principles` body: `@id Title`, then the paragraph under it.

    The grammar is deliberately thinner than Markdown. A principle needs an
    identity the prose can point at, a title short enough to be read in a
    popover, and a body of running text—nothing that a heading, a list or a
    nested directive would add belongs in a sentence the report repeats by
    number.
    """
    principles: List[Principle] = []
    body: List[str] = []

    def close() -> None:
        if principles:
            principles[-1].body_markdown = "\n".join(body).strip()

    for raw in text.splitlines():
        match = PRINCIPLE_ITEM.match(raw)
        if match:
            close()
            body = []
            principles.append(
                Principle(len(principles) + 1, match.group(1), match.group(2), "")
            )
            continue
        if not principles:
            if raw.strip():
                raise ReportError(
                    f"{line_hint}'::: {PRINCIPLES_BLOCK}' starts with text before "
                    "its first principle—every principle opens with a line "
                    "'@id Title'"
                )
            continue
        body.append(raw)
    close()

    if not principles:
        raise ReportError(
            f"{line_hint}'::: {PRINCIPLES_BLOCK}' declares no principle—write "
            "'@id Title' and a paragraph under it"
        )
    seen: Dict[str, int] = {}
    for item in principles:
        if item.id in seen:
            raise ReportError(
                f"{line_hint}two principles share the id '{item.id}'—a "
                "reference could not tell them apart"
            )
        seen[item.id] = item.number
        if not item.body_markdown:
            raise ReportError(
                f"{line_hint}principle '{item.id}' has a title and no text—the "
                "popover would open on nothing"
            )
    return principles


def collect_principles(blocks: Sequence[Block]) -> List[Principle]:
    """The declaration, read before anything is compiled.

    A reference may stand above the block that declares it—the principles are
    stated once, and the sections that act on them run in their own order—so
    the ids have to be known before the first substitution rather than
    discovered while walking the document.
    """
    declared = [
        block
        for block in blocks
        if block.kind == "component" and block.name == PRINCIPLES_BLOCK
    ]
    if not declared:
        return []
    if len(declared) > 1:
        raise ReportError(
            f"line {declared[1].line}: the report already declares "
            f"'::: {PRINCIPLES_BLOCK}'—principles are numbered from one list"
        )
    hint = f"line {declared[0].line}: "
    return parse_principles(declared[0].text, hint)


def substitute_principle_refs(
    text: str,
    principles: Sequence[Principle],
    seen: List[str],
    line_hint: str = "",
) -> str:
    """Replace `((id))` with the principle's number, linked into the list.

    A real link, like a note's marker: with no JavaScript, and on paper,
    following it lands on the principle it names. The popover is the screen
    reading of the same relation, not the only way to resolve it.
    """
    index = {item.id: item for item in principles}

    def replace(match: re.Match) -> str:
        key = match.group(1)
        item = index.get(key)
        if item is None:
            known = ", ".join(sorted(index)) or "no principles"
            raise ReportError(
                f"{line_hint}unknown design principle '(({key}))'—"
                f"'::: {PRINCIPLES_BLOCK}' declares {known}"
            )
        seen.append(key)
        return (
            f'<a class="pref" href="#principle-{item.number}" '
            f'data-pop-label="Principle {item.number}" '
            f'aria-describedby="principle-{item.number}" '
            f'aria-label="Design principle {item.number}: {_escape(item.title)}">'
            f"{item.label}</a>"
        )

    substituted = _outside_fences(text, lambda line: PRINCIPLE_REF.sub(replace, line))
    return substituted.replace("\\((", "((")


def _principles_html(principles: Sequence[Principle]) -> str:
    """The list every reference points into, on screen and on paper alike."""
    if not principles:
        return ""
    items = "".join(
        f'<li class="principle" id="principle-{item.number}">'
        f'<p class="principle-title">'
        f'<span class="principle-no">{item.label}</span>'
        f'<span class="principle-name">{item.title_html or _escape(item.title)}</span>'
        f"</p>"
        f'<div class="principle-body pop-body">{item.body_html}</div>'
        "</li>"
        for item in principles
    )
    return (
        '<aside class="principles" id="principles" aria-label="Design principles">'
        '<p class="principles-label">Design principles</p>'
        f'<ol class="principle-list">{items}</ol>'
        "</aside>"
    )


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

# Where `::: references` asked for the list. It can only be written once every
# citation has been numbered, which is after the whole document is compiled.
REFERENCES_PLACEHOLDER = "<!--report:references-->"


def substitute_refcites(
    text: str,
    bib: Bibliography,
    order: List[str],
    line_hint: str = "",
) -> str:
    """Replace `[@key]` with the number of the work in the reference list.

    Numbers are assigned on first citation, so the list at the end of the report
    runs in the order the reader meets the works and nobody maintains a number
    by hand. An unknown key fails the build for the same reason an unknown fact
    does: a citation that resolves to nothing is worse than no citation.
    """

    def replace(match: re.Match) -> str:
        keys = [
            part.strip().lstrip("@").strip()
            for part in re.split(r"[;,]", match.group(1))
        ]
        cited: List[Tuple[int, Reference]] = []
        for key in keys:
            entry = bib.get(key)
            if entry is None:
                known = ", ".join(sorted(bib.keys())) or "nothing"
                raise ReportError(
                    f"{line_hint}unknown reference '[@{key}]'—"
                    f"docs/report/references.bib declares {known}"
                )
            if key not in order:
                order.append(key)
            cited.append((order.index(key) + 1, entry))
        links = ", ".join(
            f'<a class="refref" href="#ref-{number}" role="doc-biblioref" '
            f'data-pop-label="[{number}]">{number}</a>'
            for number, entry in cited
        )
        return f'<span class="refcite">[{links}]</span>'

    def rewrite(line: str) -> str:
        rewritten = REFCITE.sub(replace, line)
        leftover = rewritten.replace("\\[@", "")
        if "[@" in leftover:
            raise ReportError(
                f"{line_hint}a citation is not closed on its own line: "
                f"{line.strip()!r}—keep '[@key; @other]' on one line so it can "
                "be resolved"
            )
        return rewritten

    substituted = _outside_fences(text, rewrite)
    return substituted.replace("\\[@", "[@")


def _reference_html(number: int, entry: Reference) -> str:
    """One entry, in the runs `bibliography` says IEEE prints it in.

    Every run carries its own punctuation, so the markup only wraps what is
    already correct text—the page cannot introduce a comma the plain rendering
    does not have. The DOI is printed rather than hidden behind the title: on
    paper it is the only part of the entry a reader can act on, and on screen it
    is the link.

    The entry sits in a `pop-body`, which is what a citation's popover copies,
    so the reader can read the reference and follow its DOI without leaving the
    sentence that cited it. The link opens in a new context for the same
    reason—the report keeps the reader's place.
    """
    parts = []
    for role, text in entry.segments():
        if role == "doi":
            parts.append(
                f'<a class="ref-doi" href="{_escape(entry.url)}" '
                f'target="_blank" rel="noreferrer">{_escape(text)}</a>'
            )
        else:
            parts.append(f'<span class="ref-{role}">{_escape(text)}</span>')
    return (
        f'<li class="reference" id="ref-{number}" value="{number}">'
        f'<span class="pop-body">{"".join(parts)}</span></li>'
    )


def references_html(entries: Sequence[Reference]) -> str:
    """The cited works, numbered as the prose numbered them."""
    if not entries:
        return ""
    items = "".join(
        _reference_html(number, entry) for number, entry in enumerate(entries, start=1)
    )
    return (
        '<div class="references" role="doc-bibliography">'
        f'<ol class="reference-list">{items}</ol>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Inline notes
# ---------------------------------------------------------------------------

# The marker a top-level heading leaves behind: a place where the notes of the
# section that just ended are flushed.
NOTES_MARKER = re.compile(r"<!--report:notes-->")


def _noteref_html(number: int) -> str:
    """The marker in the running text.

    A real link to the note, not a button: with no JavaScript, and on paper,
    following it lands on the text it points at. The popover is an enhancement
    that intercepts the click, not the only way to read the note.
    """
    return (
        f'<a class="noteref" id="noteref-{number}" href="#note-{number}" '
        f'role="doc-noteref" aria-describedby="note-{number}" '
        f'data-pop-label="Note {number}">'
        f"<sup>{number}</sup></a>"
    )


def _notes_html(notes: Sequence[Note]) -> str:
    """One section's notes, as the numbered list both renderings read from."""
    if not notes:
        return ""
    items = "".join(
        f'<li class="note" id="note-{note.number}">'
        f'<span class="note-body pop-body">{note.body_html}</span> '
        f'<a class="note-back" href="#noteref-{note.number}" '
        f'aria-label="Back to the text at note {note.number}">&#8617;</a></li>'
        for note in notes
    )
    return (
        '<aside class="notes" role="doc-endnotes" aria-label="Notes">'
        '<p class="notes-label">Notes</p>'
        f'<ol class="notes-list" start="{notes[0].number}">{items}</ol>'
        "</aside>"
    )


def _render_inline(text: str) -> str:
    """Render a note body as inline content—no paragraph wrapper around it."""
    html = _render_markdown(text).strip()
    if html.startswith("<p>") and html.endswith("</p>") and "<p>" not in html[3:]:
        return html[3:-4]
    return html


def extract_notes(text: str, notes: List[Note], line_hint: str = "") -> str:
    """Replace `^[body]` with its marker, appending the note to `notes`.

    Brackets are matched by counting, so a note may contain a Markdown link, and
    `\\^[` escapes the syntax. Fenced code is skipped for the same reason
    citations skip it: the report has to be able to show its own syntax.

    The body is collapsed to one line before it is rendered. A note is
    inline-level by construction—it has to fit in a popover and at the foot of a
    section—so a body that tried to open a list or a heading would be a
    formatting accident, not an authoring option.
    """
    out: List[str] = []
    fence: Optional[str] = None
    prose: List[str] = []

    def flush_prose() -> None:
        if prose:
            out.append(_scan_notes("\n".join(prose), notes, line_hint))
            prose.clear()

    for raw in text.splitlines():
        fence_match = FENCE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
                flush_prose()
            elif fence == marker:
                fence = None
            out.append(raw)
            continue
        if fence is not None:
            out.append(raw)
            continue
        prose.append(raw)
    flush_prose()
    return "\n".join(out)


def _scan_notes(chunk: str, notes: List[Note], line_hint: str) -> str:
    out: List[str] = []
    index = 0
    while True:
        start = chunk.find("^[", index)
        if start < 0:
            out.append(chunk[index:])
            return "".join(out)
        if start and chunk[start - 1] == "\\":
            out.append(chunk[index : start - 1])
            out.append("^[")
            index = start + 2
            continue

        depth = 1
        cursor = start + 2
        while cursor < len(chunk) and depth:
            if chunk[cursor] == "[":
                depth += 1
            elif chunk[cursor] == "]":
                depth -= 1
            cursor += 1
        if depth:
            raise ReportError(
                f"{line_hint}an inline note '^[' is never closed with ']'"
            )

        body = " ".join(chunk[start + 2 : cursor - 1].split())
        if not body:
            raise ReportError(f"{line_hint}an inline note '^[]' has no text")
        note = Note(len(notes) + 1, body, _render_inline(body))
        notes.append(note)
        out.append(chunk[index:start])
        out.append(_noteref_html(note.number))
        index = cursor


def place_notes(html: str, notes: Sequence[Note]) -> str:
    """Flush each section's notes under it, and any remainder at the end.

    Notes are grouped by section rather than piled at the end of the report,
    because a note is worth the interruption only while the paragraph that
    raised it is still on the page—or, on paper, at most a page away.

    Which notes belong to which section is decided from the rendered document
    rather than from the order in which they were collected: a note goes to the
    first flush marker that follows its own marker in the page. Collection runs
    a block at a time and a block may span a heading, so counting notes as they
    arrive would put a section's notes above its heading.
    """
    where = {note.number: html.find(f'id="noteref-{note.number}"') for note in notes}
    placed: set = set()

    def replace(match: re.Match) -> str:
        at = match.start()
        group = [
            note
            for note in notes
            if note.number not in placed and 0 <= where[note.number] < at
        ]
        placed.update(note.number for note in group)
        return _notes_html(group)

    out = NOTES_MARKER.sub(replace, html)
    remainder = [note for note in notes if note.number not in placed]
    if remainder:
        out = f"{out}\n{_notes_html(remainder)}"
    return out


def _renumber_headings(
    text: str, counters: List[int], flat: List[Section], used: Dict[str, int]
) -> str:
    """Turn `## Title` into a numbered, anchored heading and record the section.

    Numbering is positional, so moving a section renumbers the report and every
    cross-reference to it follows. Skipping a level is a build error: `1.0.1`
    would be nonsense, and silently inventing a parent would be worse.

    A top-level heading also closes the previous section's notes by leaving a
    marker where they belong; `place_notes` fills the markers in afterward, once
    the whole document has been rendered and every note has a position in it.
    """
    out: List[str] = []
    fence: Optional[str] = None
    for raw in text.splitlines():
        fence_match = FENCE.match(raw)
        if fence_match:
            marker = fence_match.group(1)
            fence = None if fence == marker else (fence or marker)
            out.append(raw)
            continue
        match = None if fence else HEADING.match(raw)
        if match is None:
            out.append(raw)
            continue

        depth = len(match.group(1)) - 1  # `##` is depth 1
        title = match.group(2)
        if any(counters[level] == 0 for level in range(depth - 1)):
            raise ReportError(
                f"heading '{title}' skips a level—a depth-{depth} heading needs "
                "a parent heading above it"
            )
        counters[depth - 1] += 1
        for deeper in range(depth, len(counters)):
            counters[deeper] = 0
        number = ".".join(str(value) for value in counters[:depth])
        slug = _slug(title, used)
        flat.append(Section(number, depth, title, slug))

        if depth == 1:
            out.extend(["", "<!--report:notes-->", ""])

        tag = f"h{depth + 1}"
        out.extend(
            [
                "",
                f'<{tag} id="{slug}" class="sec sec-{depth}">'
                f'<a class="secno" href="#{slug}">{number}</a>'
                f"<span>{_escape(title)}</span></{tag}>",
                "",
            ]
        )
    return "\n".join(out)


def _tree(flat: Sequence[Section]) -> List[Section]:
    """Nest the flat heading list by depth, for the contents and the sidebar."""
    roots: List[Section] = []
    stack: List[Section] = []
    for section in flat:
        while stack and stack[-1].level >= section.level:
            stack.pop()
        if stack:
            stack[-1].children.append(section)
        else:
            roots.append(section)
        stack.append(section)
    return roots


def _render_markdown(text: str) -> str:
    return str(
        markdown.markdown(
            text,
            extensions=MARKDOWN_EXTENSIONS,
            extension_configs=MARKDOWN_CONFIGS,
            output_format="html",
        )
    )


def _callout_html(block: Block, inner: str) -> str:
    label = CALLOUTS[block.name]
    title = block.params.get("title", label)
    return (
        f'<aside class="callout callout-{block.name}">'
        f'<p class="callout-label">{_escape(title)}</p>'
        f'<div class="callout-body">{inner}</div>'
        "</aside>"
    )


def _mount_html(mount: Mount, inner: str) -> str:
    attrs = [
        f'data-component="{_escape(mount.component)}"',
        f'data-figure="{mount.figure_start}"',
        f'data-table="{mount.table_start}"',
    ]
    for key, value in sorted(mount.params.items()):
        attrs.append(f'data-{_escape(key)}="{_escape(value)}"')
    note = f'<div class="widget-note">{inner}</div>' if inner.strip() else ""
    return (
        f'<div class="widget" {" ".join(attrs)}>{note}'
        '<div class="widget-mount"></div>'
        f'<p class="widget-fallback">This block is computed when the report is '
        f"built. Enable JavaScript, or rebuild with "
        f"<code>python scripts/generate_report.py</code>.</p>"
        "</div>"
    )


def _toc_html(sections: Sequence[Section]) -> str:
    def render(items: Sequence[Section]) -> str:
        parts = ['<ol class="toc-list">']
        for item in items:
            parts.append(
                f'<li><a href="#{item.slug}">'
                f'<span class="toc-no">{item.number}</span>'
                f"<span>{_escape(item.title)}</span></a>"
            )
            if item.children:
                parts.append(render(item.children))
            parts.append("</li>")
        parts.append("</ol>")
        return "".join(parts)

    return f'<nav class="toc" aria-label="Contents">{render(sections)}</nav>'


def emits(component: str, params: Dict[str, str]) -> Tuple[int, int]:
    """How many numbered captions a component is declared to produce."""
    spec = COMPONENTS[component]
    return spec.figures, spec.tables


def compile_report(
    source: str,
    facts: Dict[str, Fact],
    source_path: str = "docs/report/report.md",
    bib: Optional[Bibliography] = None,
) -> Document:
    """Authored Markdown in, page body plus mount manifest out."""
    front, body, offset = split_front_matter(source)
    blocks = split_blocks(body, offset)
    works = bibliography.default() if bib is None else bib

    citations: List[str] = []
    figrefs: List[str] = []
    refcites: List[str] = []
    prefs: List[str] = []
    principles = collect_principles(blocks)
    flat: List[Section] = []
    mounts: List[Mount] = []
    notes: List[Note] = []
    counters = [0, 0, 0]
    slugs: Dict[str, int] = {}
    figure = 1
    table = 1
    parts: List[str] = []
    # The contents can only be written once every heading is known, so the
    # `::: toc` block leaves a marker and is filled in at the end.
    toc_placeholder = "<!--report:toc-->"
    references_seen = False

    for block in blocks:
        hint = f"line {block.line}: " if block.line else ""
        # Figure references first: a reference's phrase is plain prose, and a
        # citation inside one should still resolve.
        text = substitute_figrefs(block.text, figrefs, hint)
        text = substitute_citations(text, facts, citations, hint)
        text = substitute_refcites(text, works, refcites, hint)
        text = substitute_principle_refs(text, principles, prefs, hint)
        # Notes last: a note may cite a measurement, a work or point into the
        # figure, and the marker it leaves behind is HTML none of those three
        # may walk into.
        text = extract_notes(text, notes, hint)

        if block.kind == "markdown":
            parts.append(
                _render_markdown(_renumber_headings(text, counters, flat, slugs))
            )
            continue

        inner = _render_markdown(_renumber_headings(text, counters, flat, slugs))

        if block.kind == "callout":
            parts.append(_callout_html(block, inner))
            continue

        if block.name == PRINCIPLES_BLOCK:
            # Re-read the block now that its text carries the substitutions, and
            # fill the objects the references were already resolved against.
            for declared, resolved in zip(principles, parse_principles(text, hint)):
                declared.title_html = _render_inline(resolved.title)
                declared.body_html = _render_markdown(resolved.body_markdown)
            parts.append(_principles_html(principles))
            continue

        if block.name == "toc":
            parts.append(toc_placeholder)
            continue

        if block.name == "references":
            if references_seen:
                raise ReportError(f"{hint}the report already prints '::: references'")
            references_seen = True
            parts.append(inner)
            parts.append(REFERENCES_PLACEHOLDER)
            continue

        spec = COMPONENTS.get(block.name)
        if spec is None:
            raise ReportError(
                f"{hint}unknown component '{block.name}'—known components are "
                + ", ".join(sorted(COMPONENTS))
            )
        missing = [key for key in spec.required if key not in block.params]
        if missing:
            raise ReportError(f"{hint}'::: {block.name}' needs {', '.join(missing)}")
        unknown = [
            key
            for key in block.params
            if key not in spec.required and key not in spec.optional
        ]
        if unknown:
            raise ReportError(
                f"{hint}'::: {block.name}' does not take {', '.join(sorted(unknown))}"
            )
        mount = Mount(block.name, dict(block.params), text, figure, table, block.line)
        figures, tables = emits(block.name, mount.params)
        figure += figures
        table += tables
        mounts.append(mount)
        parts.append(_mount_html(mount, inner))

    sections = _tree(flat)
    references = [entry for entry in (works.get(key) for key in refcites) if entry]
    html = place_notes("\n".join(parts), notes)
    html = html.replace(toc_placeholder, _toc_html(sections))
    html = html.replace(REFERENCES_PLACEHOLDER, references_html(references))
    return Document(
        front,
        html,
        sections,
        mounts,
        citations,
        source_path,
        figrefs,
        notes,
        refcites,
        references,
        references_seen,
        principles,
        prefs,
        parse_authors(front.get("authors", "")),
    )
