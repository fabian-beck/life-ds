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
    turns it into a two-way link between the sentence and the drawing.

`::: component key=value`
    A mount point for computed content. The block's own body is authored prose
    that introduces the component and is kept above it.

`::: note` / `::: aside` / `::: decision` / `::: limitation`
    Callouts rendered here in Python; they hold authored text only.

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

from . import teaser
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
            "artifacts",
            "The files one pipeline reads and writes.",
            required=("lane",),
            tables=1,
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
PARAM = re.compile(r"""([a-z][a-z0-9_-]*)=(?:"([^"]*)"|'([^']*)'|(\S+))""")
FENCE = re.compile(r"^\s*(```|~~~)")


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
class Document:
    front: Dict[str, str]
    html: str
    sections: List[Section]
    mounts: List[Mount]
    citations: List[str]
    source_path: str
    figrefs: List[str] = field(default_factory=list)
    notes: List[Note] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.front.get("title", "Technical report")

    def to_json(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.front.get("subtitle", ""),
            "abstract": self.front.get("abstract", ""),
            "source": self.source_path,
            "sections": [section.to_json() for section in self.sections],
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


def substitute_figrefs(text: str, seen: List[str], line_hint: str = "") -> str:
    """Replace `[[part|phrase]]` with a control that points into the figure.

    The phrase stays ordinary prose—the sentence has to read the same with the
    figure, without it, and on paper—so the element carries the relation and
    nothing else. Resolving the id here rather than in the page is what makes a
    reference into the figure a build-time claim: a part that was renamed or
    removed stops the build instead of leaving a phrase that lights nothing.
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
            f'{_escape(part.label)} in the figure">{_escape(label)}</button>'
        )

    substituted = _outside_fences(text, lambda line: FIGREF.sub(replace, line))
    return substituted.replace("\\[[", "[[")


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
        f'role="doc-noteref" aria-describedby="note-{number}">'
        f"<sup>{number}</sup></a>"
    )


def _notes_html(notes: Sequence[Note]) -> str:
    """One section's notes, as the numbered list both renderings read from."""
    if not notes:
        return ""
    items = "".join(
        f'<li class="note" id="note-{note.number}">'
        f'<span class="note-body">{note.body_html}</span> '
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
) -> Document:
    """Authored Markdown in, page body plus mount manifest out."""
    front, body, offset = split_front_matter(source)
    blocks = split_blocks(body, offset)

    citations: List[str] = []
    figrefs: List[str] = []
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

    for block in blocks:
        hint = f"line {block.line}: " if block.line else ""
        # Figure references first: a reference's phrase is plain prose, and a
        # citation inside one should still resolve.
        text = substitute_figrefs(block.text, figrefs, hint)
        text = substitute_citations(text, facts, citations, hint)
        # Notes last: a note may cite a measurement or point into the figure,
        # and the marker it leaves behind is HTML neither of those two may walk
        # into.
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

        if block.name == "toc":
            parts.append(toc_placeholder)
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
    html = place_notes("\n".join(parts), notes)
    html = html.replace(toc_placeholder, _toc_html(sections))
    return Document(
        front, html, sections, mounts, citations, source_path, figrefs, notes
    )
