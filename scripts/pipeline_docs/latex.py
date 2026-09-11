#!/usr/bin/env python3
"""Emit the technical report as LaTeX, for a PDF whose figures float.

`render.py` writes the page, and the page prints itself through the `@media
print` half of `style.css`. That rendering has one limit no stylesheet can
lift: CSS has no page floats. A figure that does not fit the rest of a sheet
is pushed whole onto the next one, and the space it leaves behind stays
empty—measured at two and a half of the printed report's twenty-four pages.
LaTeX places a figure at the next position where it fits and lets the text run
on, which is what this second rendering is for.

The rendering reads what the page reads: the body `report.py` compiled and the
payload `model.py` built. It does not compile the Markdown a second time. The
compiled body is walked as a tree, and each element is written in LaTeX, so a
phrase, a citation, a note, and a reference reach paper exactly as they reach
the screen, and a new authoring construct is added once, in `report.py`, and
then given a LaTeX form here. Computed blocks are written by a roster of the
same names as the one in `app.js`, and the two rosters are checked against
each other.

What the browser draws, the browser prints. The teaser and the pipeline charts
are laid out in `app.js`, and a second layout in Python would be a second
drawing to keep in step. `scripts/export_report_figures.mjs` prints each of
them to a vector PDF of its own size; this module includes the file and records
the fingerprint of the payload it was printed from, so a chart that moved is
reported stale exactly as a screenshot is.

Styling follows the page's own. The tokens under `:root` in `style.css`—the
four kind colors, the rules, the inks—are read at build time, so the two
renderings cannot drift apart in color. The running text is set in Charter,
the second face of the page's serif stack; captions, legends, tables, and
labels in a sans-serif; black on white, hairline rules, square corners, and
color for the step kind alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from . import teaser
from .render import DRAFT_LEAD, DRAFT_TEXT
from .report import Document, Mount, Note

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / "assets"
LATEX_DIR = REPO_ROOT / "docs" / "report" / "latex"
FIGURES_DIR = LATEX_DIR / "figures"
FIGURES_INDEX = "index.json"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export_report_figures.mjs"
DEFAULT_PAGE = REPO_ROOT / "docs" / "report" / "index.html"

# Where the screenshots live, relative to the `.tex`: the pictures are shared
# with the page rather than copied beside the LaTeX source.
SCREENSHOTS_RELATIVE = "../screenshots/"

# A capture no wider than this prints at its own size, as the page shows it in
# the margin; a wider one takes the room a drawing takes. The same threshold
# `MARGIN_FIGURE_MAX` in `app.js` uses to classify a screenshot.
MARGIN_FIGURE_MAX = 500

CSS_PX_PER_MM = 96 / 25.4


class LatexError(ValueError):
    """A fault that stops the LaTeX rendering, reported with its cause."""


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------

# The page's color tokens and the names the LaTeX preamble defines them under.
# xcolor names carry no hyphen, since `-` is an operator in a color expression.
COLOR_TOKENS: Dict[str, str] = {
    "paper": "paper",
    "surface": "surface",
    "ink": "ink",
    "ink-2": "inktwo",
    "muted": "muted",
    "faint": "faint",
    "rule": "rule",
    "rule-soft": "rulesoft",
    "rule-strong": "rulestrong",
    "draft-wash": "draftwash",
    "draft-line": "draftline",
    "draft-ink": "draftink",
    "kind-ai": "kindai",
    "kind-deterministic": "kinddeterministic",
    "kind-external": "kindexternal",
    "kind-image": "kindimage",
}

KIND_COLORS: Dict[str, str] = {
    "ai": "kindai",
    "deterministic": "kinddeterministic",
    "external": "kindexternal",
    "image": "kindimage",
}

ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.DOTALL)
TOKEN = re.compile(r"--([a-z0-9-]+)\s*:\s*([^;]+);")
HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{6})$")


def design_tokens(css: Optional[str] = None) -> Dict[str, str]:
    """The `--name: value` pairs declared under `:root` in the stylesheet."""
    text = css if css is not None else (ASSETS / "style.css").read_text("utf-8")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    match = ROOT_BLOCK.search(text)
    if match is None:
        raise LatexError("style.css declares no :root block to read tokens from")
    return {
        name: " ".join(value.split()) for name, value in TOKEN.findall(match.group(1))
    }


def color_definitions(tokens: Dict[str, str]) -> List[str]:
    """One `\\definecolor` per page color, in the page's own values."""
    lines = []
    for token, name in COLOR_TOKENS.items():
        value = tokens.get(token)
        if value is None:
            raise LatexError(f"style.css no longer declares --{token}")
        match = HEX_COLOR.match(value)
        if match is None:
            raise LatexError(f"--{token} is {value!r}, not a six-digit hex color")
        lines.append(f"\\definecolor{{{name}}}{{HTML}}{{{match.group(1).upper()}}}")
    return lines


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------

SPECIALS: Dict[str, str] = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    '"': r"\textquotedbl{}",
    "\u2019": "'",
    "\u2018": "`",
    "\u201c": "``",
    "\u201d": "''",
    "\u2014": "---",
    "\u2013": "--",
    "\u2026": r"\ldots{}",
    "\u00a0": "~",
    "\u00b7": r"\textperiodcentered{}",
    "\u00d7": r"\texttimes{}",
    "\u2212": r"$-$",
    "\u2192": r"$\rightarrow$",
    "\u2190": r"$\leftarrow$",
    "\u2264": r"$\leq$",
    "\u2265": r"$\geq$",
    "\u2248": r"$\approx$",
    "\u00b0": r"\textdegree{}",
    "\u20ac": r"\texteuro{}",
    "\u2011": r"\mbox{-}",
    "\u200b": "",
    "\u21a9": "",
}

WHITESPACE = re.compile(r"\s+")


def escape(text: str) -> str:
    """Plain text as LaTeX reads it: every special character defused."""
    return "".join(SPECIALS.get(char, char) for char in text)


def escape_code(text: str) -> str:
    """Text for `\\texttt`: escaped, and with its hyphens kept apart.

    Two hyphens in a row are a ligature in the typewriter face of T1-encoded
    fonts too, and a command-line flag printed as an en dash names nothing. A
    line may break after a hyphen, which is where a model name in a narrow
    table column has to break.
    """
    return escape(text).replace("-", "{-}\\allowbreak{}")


def escape_url(url: str) -> str:
    """An address for `\\href`, which reads the URL almost verbatim."""
    return url.replace("\\", "\\\\").replace("%", "\\%").replace("#", "\\#")


# ---------------------------------------------------------------------------
# The compiled body as a tree
# ---------------------------------------------------------------------------

VOID_TAGS = {"br", "hr", "img", "path", "meta", "link", "input", "circle", "rect"}


@dataclass
class Node:
    tag: str
    attrs: Dict[str, str]
    children: List[Union["Node", str]]

    def classes(self) -> List[str]:
        return self.attrs.get("class", "").split()

    def has_class(self, name: str) -> bool:
        return name in self.classes()

    def text(self) -> str:
        return "".join(
            child if isinstance(child, str) else child.text() for child in self.children
        )

    def find(self, tag: str) -> Optional["Node"]:
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    return child
                found = child.find(tag)
                if found is not None:
                    return found
        return None

    def find_all(self, predicate: Callable[["Node"], bool]) -> List["Node"]:
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if predicate(child):
                    found.append(child)
                found.extend(child.find_all(predicate))
        return found


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, [])
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        node = Node(tag, {key: value or "" for key, value in attrs}, [])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        self.stack[-1].children.append(
            Node(tag, {key: value or "" for key, value in attrs}, [])
        )

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    builder = _Builder()
    builder.feed(html)
    builder.close()
    return builder.root


# ---------------------------------------------------------------------------
# Vector figures, printed by the browser
# ---------------------------------------------------------------------------

# The fields of a step the chart draws. The rest—its summary, its source
# position, its schema—reaches the step note and the appendix, not the drawing.
DRAWN_STEP_FIELDS = (
    "id",
    "label",
    "column",
    "lane",
    "group",
    "kind",
    "depends_on",
    "model",
    "effort",
    "byline",
    "model_note",
    "calls_per_run",
)


@dataclass(frozen=True)
class Figure:
    """One drawn figure the browser prints for the LaTeX rendering."""

    id: str
    file: str
    selector: str
    fingerprint: str


@dataclass
class Export:
    """What was written for a figure, the last time it was printed."""

    file: str
    fingerprint: str
    exported: str
    width: int = 0
    height: int = 0
    bytes: int = 0

    def to_json(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "fingerprint": self.fingerprint,
            "exported": self.exported,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
        }


def _fingerprint(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def teaser_figure(payload: Dict[str, Any]) -> Figure:
    facts = payload.get("facts") or {}
    drawn = {
        "scene": payload.get("teaser"),
        "facts": {
            key: (facts.get(key) or {}).get("display") for key in teaser.fact_keys()
        },
    }
    return Figure(
        "teaser",
        "teaser.pdf",
        '.widget[data-component="teaser"] svg.teaser-svg',
        _fingerprint(drawn),
    )


def pipeline_figure(lane: str, payload: Dict[str, Any]) -> Figure:
    steps = [
        {key: step.get(key) for key in DRAWN_STEP_FIELDS}
        for step in payload.get("steps", [])
        if step.get("column") == lane
    ]
    drawn_ids = {step["id"] for step in steps}
    groups = [
        group
        for group in payload.get("groups", [])
        if any(step_id in drawn_ids for step_id in group.get("steps", []))
    ]
    drawn = {
        "lane": (payload.get("lanes") or {}).get(lane),
        "steps": steps,
        "groups": groups,
        "kinds": payload.get("kinds"),
    }
    return Figure(
        f"pipeline-{lane}",
        f"pipeline-{lane}.pdf",
        f'.widget[data-component="pipeline"][data-lane="{lane}"] .chart-scroll > svg',
        _fingerprint(drawn),
    )


def figures_of(document: Document, payload: Dict[str, Any]) -> List[Figure]:
    """The drawn figures the report mounts, in document order."""
    figures: List[Figure] = []
    for mount in document.mounts:
        if mount.component == "teaser":
            figures.append(teaser_figure(payload))
        elif mount.component == "pipeline":
            figures.append(pipeline_figure(mount.params["lane"], payload))
    return figures


def load_figure_index(directory: Path = FIGURES_DIR) -> Dict[str, Export]:
    path = directory / FIGURES_INDEX
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        figure_id: Export(
            file=str(entry.get("file", "")),
            fingerprint=str(entry.get("fingerprint", "")),
            exported=str(entry.get("exported", "")),
            width=int(entry.get("width", 0) or 0),
            height=int(entry.get("height", 0) or 0),
            bytes=int(entry.get("bytes", 0) or 0),
        )
        for figure_id, entry in (data.get("figures") or {}).items()
    }


def save_figure_index(
    exports: Dict[str, Export], directory: Path = FIGURES_DIR
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / FIGURES_INDEX
    data = {
        "note": (
            "Written by scripts/generate_report.py --figures. Each entry records "
            "the fingerprint of the payload the figure was printed from, which "
            "is how a build knows the drawing is stale."
        ),
        "figures": {
            figure_id: exports[figure_id].to_json() for figure_id in sorted(exports)
        },
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def figure_status(
    figure: Figure, exports: Dict[str, Export], directory: Path = FIGURES_DIR
) -> str:
    """`current`, `stale` (the drawing's data moved) or `missing`."""
    export = exports.get(figure.id)
    if export is None or not (directory / export.file).is_file():
        return "missing"
    if export.fingerprint != figure.fingerprint:
        return "stale"
    return "current"


STALE = "stale"
ALL = "all"


def select_figures(
    figures: Sequence[Figure],
    selector: str,
    exports: Optional[Dict[str, Export]] = None,
    directory: Path = FIGURES_DIR,
) -> List[Figure]:
    """Which figures a `--figures` argument asks for."""
    if selector == ALL:
        return list(figures)
    known = exports if exports is not None else load_figure_index(directory)
    if selector == STALE:
        return [
            figure
            for figure in figures
            if figure_status(figure, known, directory) != "current"
        ]
    wanted = [name.strip() for name in selector.split(",") if name.strip()]
    ids = {figure.id for figure in figures}
    unknown = [name for name in wanted if name not in ids]
    if unknown:
        raise LatexError(
            "the report draws no figure named "
            + ", ".join(sorted(unknown))
            + "—it draws "
            + (", ".join(sorted(ids)) or "none")
        )
    return [figure for figure in figures if figure.id in wanted]


def figure_problems(
    figures: Sequence[Figure], directory: Path = FIGURES_DIR
) -> List[Tuple[str, str, str]]:
    """What is wrong with the printed figures, as `(severity, where, message)`.

    A missing drawing is a warning rather than an error, unlike a missing
    screenshot: the page builds without it, and only the LaTeX rendering, which
    `compile_report_latex.py` refuses to run without it, is affected. A stale
    one names the command that reprints it.
    """
    exports = load_figure_index(directory)
    problems: List[Tuple[str, str, str]] = []
    for figure in figures:
        status = figure_status(figure, exports, directory)
        where = f"latex/figures/{figure.file}"
        if status == "missing":
            problems.append(
                (
                    "warning",
                    where,
                    "the LaTeX rendering includes this drawing, and it has not "
                    "been printed—run 'python scripts/generate_report.py "
                    f"--figures {figure.id}'",
                )
            )
        elif status == "stale":
            problems.append(
                (
                    "warning",
                    where,
                    "the data this drawing is made of changed since it was "
                    "printed—reprint it with 'python scripts/generate_report.py "
                    f"--figures {figure.id}'",
                )
            )
    return problems


def figure_manifest(
    figures: Sequence[Figure], page: Path = DEFAULT_PAGE, directory: Path = FIGURES_DIR
) -> Dict[str, Any]:
    """What the browser driver needs, and nothing about the report."""
    return {
        "input": page.as_posix(),
        "outDir": directory.as_posix(),
        "figures": [
            {"id": figure.id, "file": figure.file, "selector": figure.selector}
            for figure in figures
        ],
    }


def export_figures(
    figures: Sequence[Figure],
    page: Path = DEFAULT_PAGE,
    directory: Path = FIGURES_DIR,
    timeout: int = 300,
    verbose: bool = False,
) -> Tuple[Dict[str, Export], List[str]]:
    """Print the drawn figures of the built page; return exports and failures.

    The printing is Node's, for the reason the screenshots are: the repository
    already carries Playwright, and the drawings exist only in a browser. This
    side owns what a figure is and whether it is current.
    """
    directory.mkdir(parents=True, exist_ok=True)
    exports = load_figure_index(directory)
    if not figures:
        return exports, []
    if not page.is_file():
        raise LatexError(
            f"no built page at {page}—the figures are printed from it, so build "
            "it first"
        )

    with tempfile.TemporaryDirectory() as workspace:
        manifest_path = Path(workspace) / "figures.json"
        results_path = Path(workspace) / "results.json"
        manifest_path.write_text(
            json.dumps(figure_manifest(figures, page, directory), indent=2),
            encoding="utf-8",
        )
        command = [
            os.environ.get("NODE", "node"),
            str(EXPORT_SCRIPT),
            "--manifest",
            str(manifest_path),
            "--results",
            str(results_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                timeout=timeout,
                check=False,
                stdout=None if verbose else subprocess.PIPE,
                stderr=None if verbose else subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            raise LatexError(
                "node was not found—the figures are printed through "
                f"{EXPORT_SCRIPT.relative_to(REPO_ROOT).as_posix()}"
            )
        except subprocess.TimeoutExpired:
            raise LatexError(f"printing the figures did not finish within {timeout}s")
        if completed.returncode != 0 and not results_path.is_file():
            output = (completed.stdout or "").strip()
            raise LatexError(
                "printing the figures failed"
                + (f":\n{_indent(output)}" if output else " with no output")
            )
        if not verbose and completed.stdout:
            print(_indent(completed.stdout.strip()))
        results = json.loads(results_path.read_text(encoding="utf-8"))

    by_id = {figure.id: figure for figure in figures}
    failures: List[str] = []
    for result in results.get("figures", []):
        figure = by_id.get(result.get("id", ""))
        if figure is None:
            continue
        if result.get("error"):
            failures.append(f"{figure.id}: {result['error']}")
            continue
        exports[figure.id] = Export(
            file=figure.file,
            fingerprint=figure.fingerprint,
            exported=str(result.get("exported", "")),
            width=int(result.get("width", 0) or 0),
            height=int(result.get("height", 0) or 0),
            bytes=int(result.get("bytes", 0) or 0),
        )
    save_figure_index(exports, directory)
    return exports, failures


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())


# ---------------------------------------------------------------------------
# Glyphs
# ---------------------------------------------------------------------------


class GlyphBook:
    """Every icon the document draws, defined once in the preamble.

    An icon is Material Design path data, which TikZ draws through its
    `svg.path` library, so the concept glyphs are vector marks in the PDF as
    they are on the page, and the same path data stands behind both. The path
    is drawn in canvas points inside its 24-unit frame and the frame resized
    to one em of the type around it, which is the size the page draws it at. The
    definitions are collected while the body is written and emitted ahead of
    it, each under the id of the concept it belongs to.
    """

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.names: Dict[str, str] = {}
        self.paths: Dict[str, str] = {}
        self.by_path = {
            concept["path"]: concept["id"]
            for concept in payload.get("concepts", [])
            if concept.get("path")
        }

    def macro(self, path: str) -> str:
        if not path:
            return ""
        name = self.names.get(path)
        if name is None:
            name = self.by_path.get(path) or f"mark{len(self.names) + 1}"
            self.names[path] = name
            self.paths[name] = path
        return f"\\glyphof{{{name}}}"

    def definitions(self) -> List[str]:
        return [
            f"\\expandafter\\newcommand\\csname glyph@{name}\\endcsname"
            f"{{\\glyph{{{self.paths[name]}}}}}"
            for name in sorted(self.paths)
        ]


# ---------------------------------------------------------------------------
# Writing the body
# ---------------------------------------------------------------------------

BLOCK_TAGS = {
    "p",
    "div",
    "ul",
    "ol",
    "dl",
    "li",
    "dt",
    "dd",
    "table",
    "pre",
    "blockquote",
    "aside",
    "nav",
    "section",
    "figure",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

HEADINGS = {"h2": "section", "h3": "subsection", "h4": "subsubsection"}


def sentence(text: str) -> str:
    """A caption as `caption()` in `app.js` prints it: closed with a full stop."""
    trimmed = text.strip()
    return trimmed if re.search(r"[.!?]$", trimmed) else trimmed + "."


class Writer:
    """Walks the compiled body and writes each element in LaTeX."""

    def __init__(self, payload: Dict[str, Any], document: Document) -> None:
        self.payload = payload
        self.document = document
        self.glyphs = GlyphBook(payload)
        self.notes: Dict[int, Note] = {note.number: note for note in document.notes}
        self.mounts = list(document.mounts)
        self.mounted = 0
        self.steps_by_id = {step["id"]: step for step in payload.get("steps", [])}
        self.artifacts_by_id = {
            artifact["id"]: artifact for artifact in payload.get("artifacts", [])
        }
        self.concepts_by_id = {
            concept["id"]: concept for concept in payload.get("concepts", [])
        }
        self.pipeline_lanes = [
            mount.params["lane"]
            for mount in document.mounts
            if mount.component == "pipeline"
        ]

    # ------------------------------------------------------------- blocks

    def blocks(self, nodes: Sequence[Union[Node, str]]) -> str:
        """Block-level content: paragraphs, lists, headings, mounts."""
        out: List[str] = []
        run: List[Union[Node, str]] = []

        def flush() -> None:
            if run:
                text = self.inline(run).strip()
                if text:
                    out.append(text + "\n\n")
                run.clear()

        for node in nodes:
            if isinstance(node, str) or node.tag not in BLOCK_TAGS:
                run.append(node)
                continue
            flush()
            out.append(self.block(node))
        flush()
        return "".join(out)

    def block(self, node: Node) -> str:
        tag = node.tag
        if tag in HEADINGS and node.has_class("sec"):
            return self.heading(node)
        if tag == "p":
            if node.has_class("widget-fallback"):
                return ""
            text = self.inline(node.children).strip()
            return f"{text}\n\n" if text else ""
        if tag in ("ul", "ol"):
            return self.list(node)
        if tag == "dl":
            return self.description(node)
        if tag == "li":
            return self.blocks(node.children)
        if tag == "table":
            return self.table(node)
        if tag == "pre":
            return (
                "\\begin{verbatim}\n"
                + node.text().strip("\n")
                + "\n\\end{verbatim}\n\n"
            )
        if tag == "blockquote":
            return "\\begin{quote}\n" + self.blocks(node.children) + "\\end{quote}\n\n"
        if tag == "hr":
            return "\\noindent\\textcolor{rule}{\\rule{\\linewidth}{0.4pt}}\n\n"
        if tag == "aside":
            if node.has_class("callout"):
                return self.callout(node)
            # A section's printed notes: on paper they are footnotes, written
            # where their markers stand.
            return ""
        if tag == "nav":
            # The contents. Dropped for the reason the print stylesheet drops
            # it: a printed document is read from its numbered headings.
            return ""
        if tag == "div":
            if node.has_class("widget"):
                return self.mount(node)
            if node.has_class("references"):
                return self.references()
            return self.blocks(node.children)
        if tag in ("h1", "h5", "h6"):
            return f"\\paragraph{{{self.inline(node.children).strip()}}}\n\n"
        return self.blocks(node.children)

    def heading(self, node: Node) -> str:
        title_node = next(
            (
                child
                for child in reversed(node.children)
                if isinstance(child, Node) and child.tag == "span"
            ),
            None,
        )
        title = escape(WHITESPACE.sub(" ", (title_node or node).text()).strip())
        label = node.attrs.get("id", "")
        command = HEADINGS[node.tag]
        anchor = f"\\label{{sec:{label}}}" if label else ""
        return f"\\{command}{{{title}}}{anchor}\n\n"

    def list(self, node: Node) -> str:
        env = "enumerate" if node.tag == "ol" else "itemize"
        lines = [f"\\begin{{{env}}}"]
        start = node.attrs.get("start")
        if env == "enumerate" and start and start.isdigit() and int(start) > 1:
            lines.append(f"\\setcounter{{enumi}}{{{int(start) - 1}}}")
        for child in node.children:
            if isinstance(child, Node) and child.tag == "li":
                lines.append("\\item " + self.blocks(child.children).strip())
        lines.append(f"\\end{{{env}}}")
        return "\n".join(lines) + "\n\n"

    def description(self, node: Node) -> str:
        lines = ["\\begin{description}"]
        for child in node.children:
            if not isinstance(child, Node):
                continue
            if child.tag == "dt":
                lines.append(f"\\item[{{{self.inline(child.children).strip()}}}]")
            elif child.tag == "dd":
                lines.append(self.blocks(child.children).strip())
        lines.append("\\end{description}")
        return "\n".join(lines) + "\n\n"

    def table(self, node: Node) -> str:
        """An authored Markdown table, set as the page sets a data table."""
        rows = node.find_all(lambda item: item.tag == "tr")
        if not rows:
            return ""
        columns = max(
            len([cell for cell in row.children if isinstance(cell, Node)])
            for row in rows
        )
        lines = [
            "\\begin{datatable}{" + "@{}" + "l" * columns + "@{}}",
            "\\tabtoprule",
        ]
        for row in rows:
            cells = [cell for cell in row.children if isinstance(cell, Node)]
            heads = all(cell.tag == "th" for cell in cells)
            texts = [
                (
                    "\\textbf{" + self.inline(cell.children).strip() + "}"
                    if heads
                    else self.inline(cell.children).strip()
                )
                for cell in cells
            ]
            lines.append(" & ".join(texts) + " \\\\")
            lines.append("\\tabheadrule" if heads else "\\tabrowrule")
        if lines[-1] == "\\tabrowrule":
            lines.pop()
        lines.append("\\tabbottomrule")
        lines.append("\\end{datatable}")
        return "\n".join(lines) + "\n\n"

    def callout(self, node: Node) -> str:
        kind = next(
            (
                name[len("callout-") :]
                for name in node.classes()
                if name.startswith("callout-")
            ),
            "note",
        )
        label = ""
        body: List[Union[Node, str]] = []
        for child in node.children:
            if isinstance(child, Node) and child.has_class("callout-label"):
                label = escape(child.text().strip())
            elif isinstance(child, Node) and child.has_class("callout-body"):
                body.extend(child.children)
            else:
                body.append(child)
        return (
            f"\\begin{{callout}}{{{kind}}}{{{label}}}\n"
            + self.blocks(body).strip()
            + "\n\\end{callout}\n\n"
        )

    # ------------------------------------------------------------- inline

    def inline(self, nodes: Sequence[Union[Node, str]]) -> str:
        return "".join(self.span(node) for node in nodes)

    def span(self, node: Union[Node, str]) -> str:
        if isinstance(node, str):
            return escape(WHITESPACE.sub(" ", node))
        tag = node.tag
        if tag in ("em", "i"):
            return f"\\emph{{{self.inline(node.children)}}}"
        if tag in ("strong", "b"):
            return f"\\textbf{{{self.inline(node.children)}}}"
        if tag in ("code", "kbd"):
            return f"\\code{{{escape_code(node.text())}}}"
        if tag == "sup":
            return f"\\textsuperscript{{{self.inline(node.children)}}}"
        if tag == "sub":
            return f"\\textsubscript{{{self.inline(node.children)}}}"
        if tag in ("s", "del"):
            return f"\\st{{{self.inline(node.children)}}}"
        if tag == "u":
            return f"\\ul{{{self.inline(node.children)}}}"
        if tag == "small":
            return f"{{\\small {self.inline(node.children)}}}"
        if tag == "q":
            return f"``{self.inline(node.children)}''"
        if tag == "br":
            return "\\\\ "
        if tag == "svg":
            if node.has_class("glyph"):
                path = node.find("path")
                return self.glyphs.macro(path.attrs.get("d", "") if path else "")
            return ""
        if tag == "img":
            src = node.attrs.get("src", "")
            if not src or src.startswith("data:"):
                return ""
            return f"\\includegraphics[width=\\linewidth]{{{src}}}"
        if tag == "a":
            return self.link(node)
        if tag == "span" and node.has_class("figcite"):
            return self.figcite(node)
        if tag == "span" and node.has_class("stepref"):
            color = KIND_COLORS.get(node.attrs.get("data-kind", ""), "ink")
            return f"\\stepref{{{color}}}{{{self.inline(node.children)}}}"
        if tag in BLOCK_TAGS:
            return self.block(node)
        return self.inline(node.children)

    def figcite(self, node: Node) -> str:
        """A figure cited by number: the label the figure environment carries."""
        cited = node.attrs.get("data-figure", "")
        component = node.attrs.get("data-component", "")
        label = f"fig:shot-{cited}" if component == "screenshot" else f"fig:{cited}"
        return f" (Figure~\\ref{{{label}}})"

    def link(self, node: Node) -> str:
        inner = self.inline(node.children)
        if node.has_class("noteref"):
            match = re.search(r"noteref-(\d+)", node.attrs.get("id", ""))
            note = self.notes.get(int(match.group(1))) if match else None
            if note is None:
                return inner
            body = self.inline(parse_html(note.body_html).children).strip()
            return f"\\footnote{{{body}}}"
        if node.has_class("refref"):
            number = node.text().strip()
            return f"\\hyperref[ref:{number}]{{{inner}}}"
        if node.has_class("secno"):
            return ""
        href = node.attrs.get("href", "")
        if node.has_class("cref"):
            # The phrase names a legend entry; the glyph it carries is the link.
            target = href[len("#concept-") :] if href.startswith("#concept-") else ""
            if target:
                return f"\\hyperref[concept:{target}]{{{inner}}}"
            return inner
        if not href or href.startswith("#"):
            return inner
        return f"\\href{{{escape_url(href)}}}{{{inner}}}"

    # ------------------------------------------------------------- mounts

    def mount(self, node: Node) -> str:
        """A computed block, written by the renderer of the mount's name."""
        component = node.attrs.get("data-component", "")
        if self.mounted >= len(self.mounts):
            raise LatexError(
                f"the body mounts '::: {component}' but the document records no "
                "mount for it"
            )
        mount = self.mounts[self.mounted]
        self.mounted += 1
        if mount.component != component:
            raise LatexError(
                f"mount {self.mounted} is '::: {component}' in the body and "
                f"'::: {mount.component}' in the document"
            )
        renderer = RENDERERS.get(component)
        if renderer is None:
            raise LatexError(
                f"no LaTeX renderer for '::: {component}'—add one to "
                "RENDERERS in pipeline_docs/latex.py"
            )
        note = ""
        for child in node.children:
            if isinstance(child, Node) and child.has_class("widget-note"):
                note = self.blocks(child.children)
        return note + renderer(self, mount)

    # --------------------------------------------------------- references

    def references(self) -> str:
        entries = self.document.references
        if not entries:
            return ""
        lines = ["\\begin{reflist}"]
        for number, entry in enumerate(entries, start=1):
            runs = []
            for role, text in entry.segments():
                if role == "doi":
                    # Breakable after its separators: a DOI is one long token,
                    # and the page lets it wrap anywhere.
                    doi = re.sub(
                        r"([./_-])",
                        lambda m: m.group(1) + "\\allowbreak{}",
                        escape(text),
                    )
                    runs.append(
                        f"\\href{{{escape_url(entry.url)}}}{{\\refdoi{{{doi}}}}}"
                    )
                elif role == "container":
                    runs.append(f"\\emph{{{escape(text)}}}")
                elif role in ("detail", "plain"):
                    runs.append(f"\\refdetail{{{escape(text)}}}")
                else:
                    runs.append(escape(text))
            lines.append(f"\\item\\label{{ref:{number}}} " + "".join(runs))
        lines.append("\\end{reflist}")
        return "\n".join(lines) + "\n\n"

    # ------------------------------------------------------------- helpers

    def kind_entries(self) -> List[Tuple[str, Dict[str, Any]]]:
        kinds = self.payload.get("kinds") or {}
        return sorted(kinds.items(), key=lambda item: item[1].get("order", 0))

    def lane_label(self, lane: str) -> str:
        lanes = self.payload.get("lanes") or {}
        return str((lanes.get(lane) or {}).get("label", lane))

    def steps_of(self, lane: str) -> List[Dict[str, Any]]:
        return [
            step for step in self.payload.get("steps", []) if step.get("column") == lane
        ]

    def artifact_list(self, ids: Sequence[str]) -> str:
        parts = []
        for artifact_id in ids:
            artifact = self.artifacts_by_id.get(artifact_id)
            if artifact is None:
                parts.append(escape(artifact_id))
                continue
            concept = self.concepts_by_id.get(artifact.get("concept") or "")
            glyph = self.glyphs.macro(concept["path"]) if concept else ""
            parts.append(f"{glyph}{escape(artifact['label'])}")
        return ", ".join(parts)

    def dependency_list(self, step: Dict[str, Any]) -> str:
        parts = []
        for dep in step.get("depends_on", []):
            parent = self.steps_by_id.get(dep.get("on", ""))
            label = parent["label"] if parent else dep.get("on", "")
            parts.append(f"\\textbf{{{escape(label)}}}---{escape(dep.get('data', ''))}")
        return "\\newline ".join(parts)

    @staticmethod
    def bare(value: Any) -> str:
        """A resolved value without where the scan found it—see `bare` in app.js."""
        return str(value).split(" (")[0].strip()

    def step_record(self, step: Dict[str, Any]) -> Dict[str, str]:
        """The record the step note and the appendix print—see `stepRecord`."""
        summary = step.get("summary") or {}
        return {
            "input": (
                escape(summary["input"])
                if summary.get("input")
                else self.dependency_list(step) or "Nothing---this step starts a branch"
            ),
            "output": (
                escape(summary["output"])
                if summary.get("output")
                else self.artifact_list(step.get("outputs") or [])
            ),
            "model": (
                f"\\code{{{escape_code(self.bare(step['model']))}}}"
                if step.get("model")
                else ""
            ),
            "effort": (
                f"\\code{{{escape_code(self.bare(step['effort']))}}}"
                if step.get("effort")
                else ""
            ),
            "calls": escape(str(step.get("calls_per_run", ""))),
        }

    @staticmethod
    def step_description(step: Dict[str, Any]) -> str:
        summary = step.get("summary") or {}
        return str(summary.get("description") or step.get("spec_summary") or "")

    def legend(self, rows: Sequence[Tuple[str, str]]) -> str:
        """A two-column legend: a marked term, and what it means."""
        lines = ["\\begin{legend}"]
        for term, meaning in rows:
            lines.append(f"{term} & {meaning} \\\\")
        lines.append("\\end{legend}")
        return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# Component renderers
# ---------------------------------------------------------------------------


def render_teaser(writer: Writer, mount: Mount) -> str:
    figure = teaser_figure(writer.payload)
    caption = str((writer.payload.get("teaser") or {}).get("caption") or teaser.CAPTION)
    return (
        "\\begin{figure}[tbp]\n"
        "\\begin{wide}\\centering\n"
        f"\\includegraphics[width=\\widewidth]{{{figure.file}}}\n"
        "\\end{wide}\n"
        f"\\caption{{{escape(sentence(caption))}}}\\label{{fig:{figure.id}}}\n"
        "\\end{figure}\n\n"
    )


def render_pipeline(writer: Writer, mount: Mount) -> str:
    lane = mount.params["lane"]
    figure = pipeline_figure(lane, writer.payload)
    drawn = {step["id"] for step in writer.steps_of(lane)}
    banded = any(
        any(step_id in drawn for step_id in group.get("steps", []))
        for group in writer.payload.get("groups", [])
    )
    caption = f"{writer.lane_label(lane)} pipeline as a dependency graph."
    if banded:
        caption += " A shaded band gathers the steps of one phase."
    return (
        "\\begin{figure}[tbp]\n"
        "\\centering\n"
        f"\\pipelinechart{{{figure.file}}}\n"
        f"\\caption{{{escape(caption)}}}\\label{{fig:{figure.id}}}\n"
        "\\end{figure}\n\n"
    )


def render_conceptlegend(writer: Writer, mount: Mount) -> str:
    rows = []
    for concept in writer.payload.get("concepts", []):
        if not concept.get("legend"):
            continue
        glyph = writer.glyphs.macro(concept.get("path", ""))
        # The label after the term: a cell that opens with one starts its
        # paragraph a line late.
        term = f"{glyph} {escape(concept['label'])}\\label{{concept:{concept['id']}}}"
        rows.append((term, escape(concept.get("blurb", ""))))
    return writer.legend(rows)


def render_screenshot(writer: Writer, mount: Mount) -> str:
    shot_id = mount.params["id"]
    shot = (writer.payload.get("screenshots") or {}).get(shot_id)
    caption = mount.params.get("caption", "")
    file = str(shot.get("file") or "") if shot else ""
    if not shot or not file:
        # A figure environment all the same, so the numbering the prose and
        # the page share holds even while the picture is missing.
        return (
            "\\begin{figure}[tbp]\n\\centering\n"
            f"\\emptynote{{No capture for \\code{{::: screenshot id="
            f"{escape_code(shot_id)}}}. The position is declared in "
            "\\code{docs/report/report.md}; the picture is taken from it by "
            "\\code{python scripts/generate\\_report.py {-}{-}shots "
            f"{escape_code(shot_id)}}}}}\n"
            f"\\caption{{{escape(sentence(caption))}}}\\label{{fig:shot-{shot_id}}}\n"
            "\\end{figure}\n\n"
        )
    width = int(shot.get("width") or 0)
    provenance = [str(shot.get("declaration") or "")]
    if shot.get("captured"):
        provenance.append("captured " + str(shot["captured"])[:10])
    if shot.get("status") != "current":
        provenance.append("the declaration has changed since---retake it")
    meta = escape("  ·  ".join(part for part in provenance if part))
    picture_file = f"{SCREENSHOTS_RELATIVE}{file}"
    if width and width <= MARGIN_FIGURE_MAX:
        # A phone held upright: two fifths of the sheet is enough to read it,
        # and leaves the page to the text the page shows it beside.
        size = f"width={width / CSS_PX_PER_MM:.1f}mm,height=0.4\\textheight,keepaspectratio"
        picture = f"\\includegraphics[{size}]{{{picture_file}}}"
        frame = f"\\centering\n\\shotframe{{{picture}}}{{{meta}}}\n"
    else:
        size = "width=\\widewidth,height=0.55\\textheight,keepaspectratio"
        picture = f"\\includegraphics[{size}]{{{picture_file}}}"
        frame = (
            "\\begin{wide}\\centering\n"
            f"\\shotframe{{{picture}}}{{{meta}}}\n"
            "\\end{wide}\n"
        )
    return (
        "\\begin{figure}[tbp]\n"
        + frame
        + f"\\caption{{{escape(sentence(caption))}}}\\label{{fig:shot-{shot_id}}}\n"
        "\\end{figure}\n\n"
    )


def render_kindlegend(writer: Writer, mount: Mount) -> str:
    rows = []
    for kind, meta in writer.kind_entries():
        swatch = f"\\swatch{{{KIND_COLORS.get(kind, 'ink')}}}"
        term = f"{swatch} {escape(str(meta.get('label', kind)))}"
        rows.append((term, escape(str(meta.get("description", "")))))
    return writer.legend(rows)


RENDERERS: Dict[str, Callable[[Writer, Mount], str]] = {
    "teaser": render_teaser,
    "pipeline": render_pipeline,
    "conceptlegend": render_conceptlegend,
    "screenshot": render_screenshot,
    "kindlegend": render_kindlegend,
}


# ---------------------------------------------------------------------------
# The appendix
# ---------------------------------------------------------------------------

APPENDIX_COLUMNS = (
    "No.",
    "Step",
    "Description",
    "Input",
    "Output",
    "Model",
    "Effort",
    "Calls per run",
)

# The share of the wide measure each column takes—the print stylesheet's
# widths for the same table, with the description giving the model and the
# effort what a name such as `gpt-image-2` needs at this size.
APPENDIX_WIDTHS = (0.05, 0.13, 0.31, 0.13, 0.13, 0.10, 0.08, 0.07)


def appendix(writer: Writer) -> str:
    """Every step's record as one table—see `renderStepAppendix` in app.js."""
    columns: List[str] = []
    for step in writer.payload.get("steps", []):
        if step.get("column") not in columns:
            columns.append(step["column"])
    if not columns:
        return ""
    figures = [f"Figure~\\ref{{fig:pipeline-{lane}}}" for lane in writer.pipeline_lanes]
    intro = (
        "One row per documented step, in the order the pipelines reach them: "
        "what the step does, what it reads and what it leaves behind, and the "
        "model, reasoning effort, and number of calls read out of its source."
    )
    if figures:
        intro += (
            " In the interactive report this is the note that opens when a step in "
            + " or ".join(figures)
            + " is clicked."
        )
    spec = "@{}" + "".join(f"S{{{width:.2f}}}" for width in APPENDIX_WIDTHS) + "@{}"
    head = " & ".join(f"\\textbf{{{escape(title)}}}" for title in APPENDIX_COLUMNS)
    lines = [
        "\\clearpage",
        "\\appendix",
        "\\section{Step details}\\label{sec:appendix-steps}",
        "",
        intro,
        "",
        "\\begin{steptable}{" + spec + "}",
        "\\tabtoprule",
        head + " \\\\",
        "\\tabheadrule",
        "\\endhead",
    ]
    index = 0
    for lane in columns:
        lines.append(
            f"\\multicolumn{{{len(APPENDIX_COLUMNS)}}}{{@{{}}l}}"
            f"{{\\lanerow{{{escape(writer.lane_label(lane))}}}}} \\\\"
        )
        lines.append("\\tablanerule")
        for step in writer.steps_of(lane):
            index += 1
            record = writer.step_record(step)
            cells = [
                f"A.{index}",
                f"\\textbf{{{escape(step['label'])}}}",
                escape(writer.step_description(step)),
                record["input"],
                record["output"],
                record["model"],
                record["effort"],
                record["calls"],
            ]
            lines.append(" & ".join(cells) + " \\\\")
            lines.append("\\tabrowrule")
    lines.pop()
    lines.append("\\tabbottomrule")
    lines.append("\\end{steptable}")
    return "\n".join(lines) + "\n\n"


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

PREAMBLE = r"""\documentclass[a4paper,11pt]{article}

%% ---- Faces. Charter is the second face of the page's serif stack; the
%% sans-serif carries what the page sets in its system face—captions, legends,
%% tables, labels—and the typewriter face the code. The same three faces
%% under either engine: as Type 1 fonts through their packages on pdfTeX, and
%% as the OpenType files those packages ship on XeTeX and LuaTeX, where the
%% Type 1 packages would leave the sans-serif and the typewriter unset.
\usepackage{iftex}
\ifPDFTeX
  \usepackage[T1]{fontenc}
  \usepackage[utf8]{inputenc}
  \usepackage{XCharter}
  \usepackage[scaled=0.92]{helvet}
  \usepackage[scaled=1.02]{inconsolata}
  \usepackage{textcomp}
\else
  \usepackage{fontspec}
  \setmainfont{XCharter}[Extension=.otf,UprightFont=*-Roman,BoldFont=*-Bold,ItalicFont=*-Italic,BoldItalicFont=*-BoldItalic]
  \setsansfont{texgyreheros}[Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic,Scale=0.92]
  \setmonofont{Inconsolatazi4}[Extension=.otf,UprightFont=*-Regular,BoldFont=*-Bold,Scale=1.02]
\fi
\usepackage{microtype}

%% ---- Page. The sheet the print stylesheet declares, with the text set to the
%% page's measure; a drawing or a wide table may reach past it to the sheet's
%% own margins, which is what `wide` does.
\usepackage[a4paper,textwidth=__TEXTWIDTH__,top=__TOP__,bottom=__BOTTOM__,footskip=9mm,hcentering]{geometry}
\newlength{\widewidth}
\setlength{\widewidth}{__WIDEWIDTH__}
\newlength{\wideoverhang}
\setlength{\wideoverhang}{\dimexpr(\widewidth-\textwidth)/2\relax}

\usepackage[table]{xcolor}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{calc}
\usepackage{array}
\usepackage{longtable}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{tikz}
\usetikzlibrary{svg.path}
\usepackage{soul}
\usepackage[skins,breakable]{tcolorbox}
\usepackage[hidelinks]{hyperref}
\graphicspath{{figures/}}

%% ---- Colors, read from the tokens under `:root` in `style.css`.
__COLORS__

%% ---- Text and floats. A figure goes to the top or the foot of the next page
%% with room for it, and shares that page with the text; only a figure of
%% most of a page stands alone on one. The measure does not indent a
%% paragraph; the space between paragraphs is what separates them.
\setcounter{topnumber}{3}
\setcounter{bottomnumber}{2}
\setcounter{totalnumber}{4}
\renewcommand{\topfraction}{0.85}
\renewcommand{\bottomfraction}{0.6}
\renewcommand{\textfraction}{0.1}
\renewcommand{\floatpagefraction}{0.75}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt plus 1pt minus 1pt}
\linespread{1.08}
\raggedbottom
\urlstyle{same}
\setlist{itemsep=2pt,topsep=4pt,leftmargin=1.6em}

%% ---- Headings: numbered, in the weight of the page's, with a rule under a
%% section as the page draws one.
\titleformat{\section}{\Large\bfseries}{\thesection}{0.8em}{}[{\color{rulestrong}\titlerule}]
\titlespacing*{\section}{0pt}{28pt plus 4pt minus 2pt}{10pt}
\titleformat{\subsection}{\large\bfseries}{\thesubsection}{0.8em}{}
\titlespacing*{\subsection}{0pt}{20pt plus 3pt minus 2pt}{6pt}
\titleformat{\subsubsection}{\normalsize\bfseries}{\thesubsubsection}{0.8em}{}
\titlespacing*{\subsubsection}{0pt}{14pt plus 2pt minus 1pt}{4pt}

%% ---- Running feet: the title and the page, as the printed page carries them.
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
\fancyfoot[L]{\sffamily\scriptsize\color{muted}__TITLE__}
\fancyfoot[R]{\sffamily\scriptsize\color{muted}\thepage{} / \pageref*{LastPage}}
\fancypagestyle{plain}{\fancyhf{}\renewcommand{\headrulewidth}{0pt}%
  \fancyfoot[L]{\sffamily\scriptsize\color{muted}__TITLE__}%
  \fancyfoot[R]{\sffamily\scriptsize\color{muted}\thepage{} / \pageref*{LastPage}}}

%% ---- Captions: sans-serif, the number bold, and under a figure the rule the
%% print stylesheet draws between a drawing and its caption. A table's caption
%% stands above the table, a figure's below it.
\DeclareCaptionFormat{ruled}{{\color{rule}\rule{\linewidth}{0.4pt}}\\[3pt]#1#2#3}
\captionsetup{font={sf,small},labelfont=bf,labelsep=period,justification=raggedright,singlelinecheck=false,skip=6pt}
\captionsetup[figure]{format=ruled,position=below}
\captionsetup[table]{position=above,skip=4pt}

%% ---- Small type: the eyebrow over a block, the line under a screenshot.
\newcommand{\eyebrow}[1]{{\sffamily\scriptsize\bfseries\color{muted}\MakeUppercase{#1}}}
\newcommand{\capstyle}{\sffamily\small}
\newcommand{\code}[1]{\texttt{#1}}
\newcommand{\refdoi}[1]{\textcolor{muted}{#1}}
\newcommand{\refdetail}[1]{\textcolor{inktwo}{#1}}
\newcommand{\emptynote}[1]{{\capstyle\color{muted}#1}}

%% ---- Marks. A concept glyph is Material Design path data, drawn by TikZ at
%% the size of the type around it; a swatch is the kind's color in a square.
\newcommand{\glyph}[1]{\raisebox{-0.14em}{\resizebox{1em}{1em}{\tikz{\path (0,0) rectangle (24pt,-24pt);\fill[color=.,yscale=-1] svg {#1};}}}}
\newcommand{\glyphof}[1]{\csname glyph@#1\endcsname}
__GLYPHS__
\newcommand{\swatch}[1]{\textcolor{#1}{\rule[-0.1ex]{0.8em}{0.8em}}}

%% ---- A step reference keeps the page's underline in the kind's color. The
%% phrase stays ordinary prose under it: it breaks and hyphenates as the
%% words around it do.
\setul{0.25ex}{1.2pt}
\newcommand{\stepref}[2]{\begingroup\setulcolor{#1}\ul{#2}\endgroup}

%% ---- The pipeline charts at one scale. The page draws both pipelines at the
%% same scale so that they can be compared directly, and so does this: every
%% chart is measured up front, the factor that fits the largest to the sheet
%% is found once, and each chart is set at that factor rather than fitted to
%% the sheet on its own. e-TeX scales a length by a ratio of two lengths in
%% one `\dimexpr`, so no floating-point number is ever written.
\newsavebox{\chartbox}
\newlength{\chartsheight}
\newlength{\chartswidth}
\newlength{\chartheight}
\newcommand{\measurechart}[1]{%
  \sbox{\chartbox}{\includegraphics{#1}}%
  \ifdim\ht\chartbox>\chartsheight\setlength{\chartsheight}{\ht\chartbox}\fi
  \ifdim\wd\chartbox>\chartswidth\setlength{\chartswidth}{\wd\chartbox}\fi}
\newcommand{\pipelinechart}[1]{%
  \sbox{\chartbox}{\includegraphics{#1}}%
  \setlength{\chartheight}{\dimexpr\chartsheight*\number\textwidth/\number\chartswidth\relax}%
  \ifdim\chartheight>0.86\textheight
    \setlength{\chartheight}{\dimexpr\ht\chartbox*\number\dimexpr0.86\textheight\relax/\number\chartsheight\relax}%
  \else
    \setlength{\chartheight}{\dimexpr\ht\chartbox*\number\textwidth/\number\chartswidth\relax}%
  \fi
  \includegraphics[height=\chartheight]{#1}}

%% ---- A block that reaches past the measure to the sheet's own margins.
\newsavebox{\widebox}
\newenvironment{wide}{\begin{lrbox}{\widebox}\begin{minipage}{\widewidth}}{\end{minipage}\end{lrbox}\noindent\makebox[\textwidth][c]{\usebox{\widebox}}}

%% ---- A data table: sans-serif, a strong rule above and below, a strong rule
%% under the head, and a soft hairline between rows—the page's table.data.
\newcommand{\tabtoprule}{\arrayrulecolor{rulestrong}\specialrule{0.8pt}{0pt}{2pt}}
\newcommand{\tabbottomrule}{\arrayrulecolor{rulestrong}\specialrule{0.8pt}{2pt}{0pt}}
\newcommand{\tabheadrule}{\arrayrulecolor{rulestrong}\specialrule{0.4pt}{1pt}{2pt}}
\newcommand{\tabrowrule}{\arrayrulecolor{rulesoft}\specialrule{0.4pt}{1pt}{1pt}}
\newcommand{\tablanerule}{\arrayrulecolor{rulestrong}\specialrule{0.4pt}{1pt}{2pt}}
\newenvironment{datatable}[1]{\sffamily\small\renewcommand{\arraystretch}{1.25}\setlength{\tabcolsep}{5pt}\begin{tabular}{#1}}{\end{tabular}}
\newcolumntype{S}[1]{>{\raggedright\arraybackslash}p{\dimexpr #1\widewidth-2\tabcolsep\relax}}
\newenvironment{steptable}[1]{\sffamily\scriptsize\renewcommand{\arraystretch}{1.2}\setlength{\tabcolsep}{4pt}\setlength{\LTleft}{-\wideoverhang}\setlength{\LTright}{-\wideoverhang}\begin{longtable}{#1}}{\end{longtable}}
\newcommand{\lanerow}[1]{\eyebrow{#1}}

%% ---- A legend: a marked term and what it means, between two hairlines.
\newenvironment{legend}{\par\vspace{4pt}\noindent\sffamily\small\renewcommand{\arraystretch}{1.2}\begin{tabular}{@{}>{\leavevmode\raggedright\arraybackslash}p{0.28\linewidth}>{\leavevmode\raggedright\arraybackslash\color{inktwo}}p{\dimexpr 0.72\linewidth-2\tabcolsep\relax}@{}}\arrayrulecolor{rule}\specialrule{0.4pt}{0pt}{3pt}}{\arrayrulecolor{rule}\specialrule{0.4pt}{3pt}{0pt}\end{tabular}\par\vspace{4pt}}

%% ---- A screenshot in its frame, with the declaration it was taken from
%% under it in the faintest type on the page.
\newcommand{\shotframe}[2]{\begin{minipage}{\linewidth}\centering{\setlength{\fboxsep}{0pt}\setlength{\fboxrule}{0.4pt}\color{rule}\fbox{\color{ink}#1}}\\[3pt]{\sffamily\tiny\color{faint}#2}\end{minipage}}

%% ---- A schema, expanded field by field.

%% ---- An authored callout: a labeled block with a rule down its left edge,
%% dashed for a limitation and faint for an aside, as the page draws them.
\newtcolorbox{calloutbox}[1][]{enhanced,breakable,sharp corners,boxrule=0pt,colback=paper,colframe=paper,left=10pt,right=0pt,top=4pt,bottom=4pt,before skip=10pt,after skip=10pt,#1}
\newenvironment{callout}[2]{%
  \def\calloutkind{#1}%
  \def\limitationkind{limitation}\def\asidekind{aside}%
  \ifx\calloutkind\limitationkind
    \begin{calloutbox}[borderline west={2pt}{0pt}{rulestrong,dashed}]%
  \else\ifx\calloutkind\asidekind
    \begin{calloutbox}[borderline west={2pt}{0pt}{rule}]%
  \else
    \begin{calloutbox}[borderline west={2pt}{0pt}{rulestrong}]%
  \fi\fi
  \eyebrow{#2}\par\vspace{2pt}\small}{\end{calloutbox}}

%% ---- The reference list, numbered as the prose numbered the works.
\newlist{reflist}{enumerate}{1}
\setlist[reflist]{label={[\arabic*]},leftmargin=2.2em,labelsep=0.6em,itemsep=3pt,font=\normalfont}

\hypersetup{pdftitle={__PDFTITLE__},pdfauthor={__PDFAUTHOR__}}
"""


def _paragraphs(text: str) -> List[str]:
    return [part.strip() for part in text.split("\n\n") if part.strip()]


def title_block(document: Document, payload: Dict[str, Any]) -> str:
    """The title, the byline, the build stamp, and the abstract."""
    lines = [
        "\\begin{tcolorbox}[enhanced,sharp corners,boxrule=0pt,colback=draftwash,"
        "colframe=draftwash,borderline south={1.5pt}{0pt}{draftline},"
        "left=6pt,right=6pt,top=6pt,bottom=6pt,before skip=0pt,after skip=18pt,"
        "fontupper=\\sffamily\\small\\color{draftink}]",
        "\\eyebrow{Draft}\\quad"
        f"\\textbf{{{escape(DRAFT_LEAD)}}} {escape(DRAFT_TEXT)}",
        "\\end{tcolorbox}",
        "",
        "\\eyebrow{Technical report}\\par\\vspace{6pt}",
        f"{{\\Huge\\bfseries {escape(document.title)}\\par}}\\vspace{{6pt}}",
    ]
    subtitle = document.front.get("subtitle", "").strip()
    if subtitle:
        lines.append(f"{{\\large {escape(subtitle)}\\par}}")
    if document.authors:
        lines.append("\\vspace{14pt}\\noindent")
        width = f"{min(0.32, 0.98 / max(len(document.authors), 1)):.2f}\\textwidth"
        for author in document.authors:
            name = f"\\textbf{{{escape(author.name)}}}"
            if author.url:
                name = f"\\href{{{escape_url(author.url)}}}{{{name}}}"
            block = [f"\\begin{{minipage}}[t]{{{width}}}\\raggedright", name]
            if author.affiliation:
                block.append(
                    "\\\\{\\sffamily\\scriptsize\\color{muted}"
                    f"{escape(author.affiliation)}}}"
                )
            if author.orcid:
                # On paper the mark links nowhere, so the iD it stands for is
                # printed, as the print stylesheet prints it.
                block.append(
                    "\\\\{\\sffamily\\tiny\\color{muted}ORCID "
                    f"\\href{{{escape_url(author.orcid_url)}}}{{{escape(author.orcid)}}}}}"
                )
            block.append("\\end{minipage}\\hfill%")
            lines.append("".join(block))
        lines.append("\\par")
    stamp = [
        part
        for part in (
            f"Version {payload['version']}" if payload.get("version") else "",
            f"commit {payload['commit']}" if payload.get("commit") else "",
        )
        if part
    ]
    if stamp:
        lines.append(
            "\\vspace{8pt}{\\sffamily\\scriptsize\\color{muted}"
            + escape("  ·  ".join(stamp))
            + "\\par}"
        )
    abstract = _paragraphs(document.front.get("abstract", ""))
    lines.append("\\vspace{14pt}{\\color{rulestrong}\\hrule}\\vspace{8pt}")
    lines.append("\\eyebrow{Abstract}\\par\\vspace{4pt}")
    if abstract:
        lines.extend(escape(part) + "\n" for part in abstract)
    else:
        lines.append("No abstract was written in the report's front matter.\n")
    lines.append("\\vspace{4pt}{\\color{rulestrong}\\hrule}\\vspace{12pt}")
    # No float above the title: the first page opens with the report's name,
    # and the teaser follows the abstract as it does on the page.
    lines.append("\\suppressfloats[t]")
    return "\n".join(lines) + "\n\n"


def colophon(document: Document) -> str:
    """The statement on AI use, after the references—see `_disclaimer_html`."""
    text = document.front.get("disclaimer", "").strip()
    if not text:
        return ""
    lines = [
        "\\vspace{24pt}{\\color{rulestrong}\\hrule}\\vspace{6pt}",
        "\\begin{minipage}{\\textwidth}\\sffamily\\footnotesize\\color{muted}",
        "\\eyebrow{Statement on AI use}\\par\\vspace{3pt}",
    ]
    lines.extend(escape(part) + "\\par" for part in _paragraphs(text))
    lines.append("\\end{minipage}")
    return "\n".join(lines) + "\n\n"


# The sheet the print stylesheet declares: A4 with 17mm side margins, and the
# text set to the page's measure—36rem at 16px is 576 CSS pixels—while a
# drawing may reach out to the sheet's own margins.
PAPER_WIDTH_MM = 210
SHEET_MARGIN_MM = 17
MEASURE_MM = round(36 * 16 / CSS_PX_PER_MM)  # 152


def render(
    payload: Dict[str, Any],
    document: Document,
    tokens: Optional[Dict[str, str]] = None,
    with_appendix: bool = True,
) -> str:
    """The whole report as one LaTeX source."""
    writer = Writer(payload, document)
    body = writer.blocks(parse_html(document.html).children)
    if writer.mounted != len(writer.mounts):
        raise LatexError(
            f"the body mounts {writer.mounted} computed blocks but the document "
            f"records {len(writer.mounts)}"
        )
    tail = appendix(writer) if with_appendix else ""
    tail += colophon(document)
    colors = "\n".join(
        color_definitions(tokens if tokens is not None else design_tokens())
    )
    glyphs = "\n".join(writer.glyphs.definitions())
    authors = ", ".join(author.name for author in document.authors)
    preamble = (
        PREAMBLE.replace("__TEXTWIDTH__", f"{MEASURE_MM}mm")
        .replace("__WIDEWIDTH__", f"{PAPER_WIDTH_MM - 2 * SHEET_MARGIN_MM}mm")
        .replace("__TOP__", "20mm")
        .replace("__BOTTOM__", "22mm")
        .replace("__COLORS__", colors)
        .replace("__GLYPHS__", glyphs)
        .replace("__TITLE__", escape(document.title))
        .replace("__PDFTITLE__", escape(document.title))
        .replace("__PDFAUTHOR__", escape(authors))
    )
    # Every pipeline chart is measured before the first is set, so that all of
    # them share the scale that fits the largest (see `\\pipelinechart`).
    measured = "".join(
        f"\\measurechart{{{figure.file}}}\n"
        for figure in figures_of(document, payload)
        if figure.id.startswith("pipeline-")
    )
    return (
        "% Generated by scripts/generate_report.py from docs/report/report.md and\n"
        "% the pipeline sources. Do not edit: rebuild the report instead.\n"
        + preamble
        + "\n\\begin{document}\n\n"
        + measured
        + ("\n" if measured else "")
        + title_block(document, payload)
        + body
        + tail
        + "\\end{document}\n"
    )


def write(
    payload: Dict[str, Any],
    path: Path,
    document: Document,
    tokens: Optional[Dict[str, str]] = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(payload, document, tokens), encoding="utf-8", newline="\n")
    return path
