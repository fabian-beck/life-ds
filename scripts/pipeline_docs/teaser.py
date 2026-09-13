#!/usr/bin/env python3
"""The teaser figure: the whole system on one canvas, in nameable parts.

The figure is declared here and drawn by `app.js`, for the same reason every
other computed block is: the page must stay a pure function of the payload. What
this module adds is that each region of the drawing has an *identity*—a stable
id, a label and a sentence—so the authored prose can point at it.

That is what makes the figure linkable. `docs/report/report.md` writes
`[[ego-network|the relationships]]`, the compiler resolves the id against `PARTS`,
and
the page then has a two-way relation between a phrase in a sentence and a
rectangle in a drawing: hovering the phrase lights the part, selecting the part
finds the phrases. An id that does not resolve fails the build, exactly as an
unknown `{{ fact }}` does—a reference into a figure is a claim about the figure,
and a claim the build cannot check is the thing this report is built to avoid.

Geometry is declared rather than laid out, because there are fourteen boxes and a
solver would be harder to read than the numbers. Coordinates are in scene units;
the page scales the whole scene to whatever width it is given, which is why the
figure needs no breakpoints and why a part can be zoomed to on its own—a
focus region is just a sub-rectangle of the same coordinate system.

A part may print a `metric`: a template over `facts.py` keys, resolved when the
page draws, so the teaser cannot state something the report would contradict.
None of the parts use it at present—the drawing shows the shape of each stage
and leaves the tallying alone—but the mechanism stays, because a figure that
quoted a value of its own would be the one place on the page a number could go
stale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import concepts

# The scene is a fixed coordinate system, not a pixel size: the page scales it
# to the width available and zooms into sub-rectangles of it on small screens.
# The four columns stand 48 units apart, which is what an edge label such as
# "material" needs to sit in the channel it crosses rather than on the boxes.
SCENE_W = 964
SCENE_H = 384

METRIC_KEY = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


@dataclass(frozen=True)
class Part:
    """One nameable region of the figure.

    `decor` names the drawing routine that fills the box—the vocabulary is
    small and closed, and `app.js` must have a routine for every name used, the
    same contract the component roster has.

    `concept` ties the part to an entry of `concepts.CONCEPTS`, which is what
    gives the figure its glyphs. The tie is the report's one visual argument
    made without words: the box that holds the relationships and the box that
    draws them carry the same mark, because they are the same thing recorded
    and shown.

    `legend` marks a part that explains the drawing rather than depicting the
    system, such as the row of step kinds. The prose may point at it but need
    not; every other part is drawn to be referenced.

    `glyph` names a vendored icon directly, for the boxes that carry a mark
    without being one of the concepts—a part of the system rather than
    something the system is about.
    """

    id: str
    label: str
    blurb: str
    box: Tuple[int, int, int, int]
    decor: str = "plain"
    metric: str = ""
    lines: Tuple[str, ...] = ()
    lane: str = ""
    parent: str = ""
    frame: str = "line"  # "line" | "soft" | "none"
    concept: str = ""
    glyph: str = ""
    legend: bool = False

    def to_json(self) -> Dict[str, Any]:
        x, y, w, h = self.box
        return {
            "id": self.id,
            "label": self.label,
            "blurb": self.blurb,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "decor": self.decor,
            "metric": self.metric,
            "lines": list(self.lines),
            "lane": self.lane,
            "parent": self.parent,
            "frame": self.frame,
            "concept": self.concept,
            "icon": (
                concepts.path_of(self.glyph)
                if self.glyph
                else concepts.icon_of(self.concept)
            ),
        }


@dataclass(frozen=True)
class Stage:
    """A heading over a band of the figure, with a rule under it.

    Four of them run across the top, naming the four things the system is made
    of. `y` keeps the heading independent of that row, so a band can be headed
    wherever it sits.
    """

    label: str
    x: int
    w: int
    y: int = 20

    def to_json(self) -> Dict[str, Any]:
        return {"label": self.label, "x": self.x, "w": self.w, "y": self.y}


@dataclass(frozen=True)
class Link:
    """An arrow between two parts.

    Only the anchors are declared. The route is computed by the page from the
    two boxes, so moving a part moves its arrows with it.
    """

    source: str
    target: str
    label: str = ""
    kind: str = "flow"  # "flow" (solid) | "call" (dotted)
    both: bool = False
    source_at: float = 0.5  # anchor height, as a fraction of the source box
    target_at: float = 0.5
    jog: float = 0.5  # where in the gap the elbow sits

    def to_json(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "kind": self.kind,
            "both": self.both,
            "source_at": self.source_at,
            "target_at": self.target_at,
            "jog": self.jog,
        }


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

STAGES: Tuple[Stage, ...] = (
    Stage("Sources", 8, 196),
    Stage("Generation", 252, 240),
    Stage("Data", 540, 180),
    Stage("Interface", 768, 188),
)

PARTS: Tuple[Part, ...] = (
    Part(
        "sources",
        "Source material",
        "Article prose, images, and place names are fetched from Wikipedia, "
        "Wikimedia Commons, Openverse, and Nominatim, and cached before any "
        "step reads them.",
        (8, 40, 196, 150),
        decor="sources",
        lines=("Article prose", "Images", "Place names"),
        concept="sources",
    ),
    Part(
        "inference",
        "AI models",
        "One hosted API answers both kinds of call: the interpretative "
        "decisions—which episodes constitute a life, which modern place a "
        "toponym denotes—are text calls returning a declared schema rather "
        "than free text, and the portraits and chapter art are drawn by the "
        "image model.",
        (8, 214, 196, 110),
        decor="traits",
        lines=(
            "OpenAI API",
            "Text generation",
            "Image generation",
        ),
        glyph="mdi-creation-outline",
    ),
    Part(
        "person-pipeline",
        "Personal story pipeline",
        "One biography end to end. After sourcing, the events are proposed, "
        "researched, and illustrated; then the style with its generated art and "
        "the ego network branch off side by side, and review, background "
        "reports, and translation close the run.",
        # Exactly the box the person story gets in the interface column: the
        # two halves of the system are drawn at the same size because neither
        # is the larger half.
        (252, 40, 240, 150),
        decor="steps",
        lane="person",
    ),
    Part(
        "meta-pipeline",
        "Meta story pipeline",
        "A theme across several finished biographies. A network branch and a map "
        "branch run independently and meet in the composition step.",
        (252, 206, 240, 128),
        decor="steps",
        lane="meta",
    ),
    Part(
        "kinds",
        "Four kinds of step",
        "A retrieval from an external source, a language model call, "
        "deterministic code, or an image model call—the classification "
        "partitions both pipelines by cost and by failure mode.",
        (8, 348, 948, 24),
        decor="kinds",
        frame="none",
        legend=True,
    ),
    Part(
        "artifacts",
        "Generated data",
        "A set of documents and images per subject and per theme, written once "
        "and read as they stand. The two halves of the system communicate "
        "through this and through nothing else: no database, no server.",
        (540, 40, 180, 294),
        decor="frame",
        frame="soft",
    ),
    Part(
        "events",
        "Life events",
        "The narrative spine: dated events with places, people, sources, and a "
        "typed icon, grouped into the chapters of a life.",
        (552, 78, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="events",
    ),
    Part(
        "narrative",
        "Narrative text",
        "The written register: an event's own description, and the article "
        "prose that surrounds a meta story's components.",
        (552, 120, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="narrative",
    ),
    Part(
        "imagery",
        "Imagery",
        "Licensed illustrations matched to the events they depict, a portrait "
        "redrawn from a reference picture in one shared style, and chapter art "
        "drawn from each chapter's concept.",
        (552, 162, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="imagery",
    ),
    Part(
        "geography",
        "Geography",
        "The historical toponyms of the events, resolved to modern coordinates "
        "a map can fly across.",
        (552, 204, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="places",
    ),
    Part(
        "ego-network",
        "Social network",
        "The subject's relationships as typed, weighted, and described ties, "
        "derived in a step of their own once the events are settled.",
        (552, 246, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="network",
    ),
    Part(
        "identity",
        "Visual identity",
        "The palette, typography, and background pattern a story is presented "
        "in, carried in the data rather than in the application.",
        (552, 288, 156, 36),
        decor="concept",
        parent="artifacts",
        concept="identity",
    ),
    Part(
        "slides",
        "Person story",
        "Full-screen slides swiped sideways one at a time—an overview, the "
        "chapters, the events, a closing slide—every position a citable "
        "address.",
        (768, 40, 188, 150),
        decor="slides",
    ),
    Part(
        "sections",
        "Meta story",
        "A continuous document read by scrolling, whose timeline, network, and "
        "map sections each keep a visualization in view while narration cards "
        "lead the reader through it.",
        (768, 206, 188, 128),
        decor="sections",
    ),
)

LINKS: Tuple[Link, ...] = (
    Link("sources", "person-pipeline", label="material", source_at=0.5),
    Link("inference", "person-pipeline", kind="call", source_at=0.35, jog=0.78),
    Link("inference", "meta-pipeline", kind="call", source_at=0.65, jog=0.56),
    Link("person-pipeline", "artifacts", label="writes", target_at=0.3, jog=0.5),
    Link(
        "meta-pipeline",
        "artifacts",
        label="reads · writes",
        both=True,
        target_at=0.72,
        jog=0.5,
    ),
    Link("artifacts", "slides", label="loads", source_at=0.25, jog=0.5),
    Link("artifacts", "sections", label="loads", source_at=0.8),
)


CAPTION = (
    "The system end to end: encyclopedic sources and model inference feed the "
    "two generation pipelines, whose data the interface reads."
)


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def part_ids() -> List[str]:
    return [part.id for part in PARTS]


def linkable_part_ids() -> List[str]:
    """The parts the prose is expected to reference: everything but a legend."""
    return [part.id for part in PARTS if not part.legend]


def part_by_id(part_id: str) -> Optional[Part]:
    for part in PARTS:
        if part.id == part_id:
            return part
    return None


def fact_keys() -> List[str]:
    """Every `facts.py` key the figure's metrics interpolate."""
    keys: List[str] = []
    for part in PARTS:
        keys.extend(METRIC_KEY.findall(part.metric))
    return sorted(dict.fromkeys(keys))


def scene() -> Dict[str, Any]:
    """The whole figure, as the payload carries it."""
    return {
        "width": SCENE_W,
        "height": SCENE_H,
        "caption": CAPTION,
        "stages": [stage.to_json() for stage in STAGES],
        "parts": [part.to_json() for part in PARTS],
        "links": [link.to_json() for link in LINKS],
    }


# ---------------------------------------------------------------------------
# Self-checks
# ---------------------------------------------------------------------------


@dataclass
class SceneProblem:
    where: str
    message: str
    severity: str = "error"


def check_scene(facts: Sequence[str] = ()) -> List[SceneProblem]:
    """Geometry and references the drawing depends on being true.

    A part outside the canvas, two siblings overlapping, a child escaping its
    parent or an arrow to a part that no longer exists all render as a figure
    that is subtly wrong rather than obviously broken, which is the worst thing
    a figure in a generated report can be.
    """
    problems: List[SceneProblem] = []
    known = {part.id: part for part in PARTS}

    seen: Dict[str, int] = {}
    for part in PARTS:
        seen[part.id] = seen.get(part.id, 0) + 1
    for part_id, count in seen.items():
        if count > 1:
            problems.append(SceneProblem("teaser", f"duplicate part id '{part_id}'"))

    for part in PARTS:
        where = f"part '{part.id}'"
        x, y, w, h = part.box
        if w <= 0 or h <= 0:
            problems.append(SceneProblem(where, "has an empty box"))
        if x < 0 or y < 0 or x + w > SCENE_W or y + h > SCENE_H:
            problems.append(SceneProblem(where, "falls outside the canvas"))
        if not part.blurb.strip():
            problems.append(SceneProblem(where, "has no blurb to show when focused"))
        if part.concept and concepts.concept_by_id(part.concept) is None:
            problems.append(
                SceneProblem(where, f"names unknown concept '{part.concept}'")
            )
        if part.decor == "concept" and not part.concept:
            problems.append(SceneProblem(where, "is drawn as a concept but names none"))
        if part.parent:
            parent = known.get(part.parent)
            if parent is None:
                problems.append(
                    SceneProblem(where, f"names unknown parent '{part.parent}'")
                )
            elif not _contains(parent.box, part.box):
                problems.append(
                    SceneProblem(where, f"is not inside its parent '{part.parent}'")
                )
        for key in METRIC_KEY.findall(part.metric):
            if facts and key not in facts:
                problems.append(SceneProblem(where, f"cites unknown fact '{key}'"))

    for first, second in _sibling_pairs():
        if _overlaps(first.box, second.box):
            problems.append(
                SceneProblem("teaser", f"parts '{first.id}' and '{second.id}' overlap")
            )

    for link in LINKS:
        for end in (link.source, link.target):
            if end not in known:
                problems.append(
                    SceneProblem("teaser", f"link names unknown part '{end}'")
                )
    return problems


def _sibling_pairs() -> List[Tuple[Part, Part]]:
    pairs: List[Tuple[Part, Part]] = []
    for index, first in enumerate(PARTS):
        for second in PARTS[index + 1 :]:
            if first.parent == second.parent:
                pairs.append((first, second))
    return pairs


def _contains(
    outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int]
) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def _overlaps(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah
