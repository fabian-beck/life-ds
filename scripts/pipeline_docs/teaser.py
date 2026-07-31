#!/usr/bin/env python3
"""The teaser figure: the whole system on one canvas, in nameable parts.

The figure is declared here and drawn by `app.js`, for the same reason every
other computed block is: the page must stay a pure function of the payload. What
this module adds is that each region of the drawing has an *identity*—a stable
id, a label and a sentence—so the authored prose can point at it.

That is what makes the figure linkable. `docs/report/report.md` writes
`[[timeline|a chronology]]`, the compiler resolves the id against `PARTS`, and
the page then has a two-way relation between a phrase in a sentence and a
rectangle in a drawing: hovering the phrase lights the part, selecting the part
finds the phrases. An id that does not resolve fails the build, exactly as an
unknown `{{ fact }}` does—a reference into a figure is a claim about the figure,
and a claim the build cannot check is the thing this report is built to avoid.

Geometry is declared rather than laid out, because there are sixteen boxes and a
solver would be harder to read than the numbers. Coordinates are in scene units;
the page scales the whole scene to whatever width it is given, which is why the
figure needs no breakpoints and why a part can be zoomed to on its own—a
focus region is just a sub-rectangle of the same coordinate system.

Numbers inside the figure are never written here. A part's `metric` is a
template over `facts.py` keys (`"{pipeline.person_steps} steps"`), resolved when
the page draws, so the teaser cannot claim a count the report would contradict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# The scene is a fixed coordinate system, not a pixel size: the page scales it
# to the width available and zooms into sub-rectangles of it on small screens.
SCENE_W = 1076
SCENE_H = 552

METRIC_KEY = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


@dataclass(frozen=True)
class Part:
    """One nameable region of the figure.

    `decor` names the drawing routine that fills the box—the vocabulary is
    small and closed, and `app.js` must have a routine for every name used, the
    same contract the component roster has.
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
        }


@dataclass(frozen=True)
class Stage:
    """A column heading: the four things the system is made of, in order."""

    label: str
    x: int
    w: int

    def to_json(self) -> Dict[str, Any]:
        return {"label": self.label, "x": self.x, "w": self.w}


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


@dataclass(frozen=True)
class Bus:
    """The one-to-many fan-out at the foot of the figure.

    A single record leaves the artifact that holds it, meets a rail, and drops
    into each encoding of it. Drawn as one shape because it is one claim.
    """

    source: str
    targets: Sequence[str]
    label: str
    drop_x: int
    rail_y: int
    label_x: int

    def to_json(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "targets": list(self.targets),
            "label": self.label,
            "drop_x": self.drop_x,
            "rail_y": self.rail_y,
            "label_x": self.label_x,
        }


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------

STAGES: Tuple[Stage, ...] = (
    Stage("Sources and inference", 8, 168),
    Stage("Generation—offline", 220, 392),
    Stage("Artifacts—static files", 656, 180),
    Stage("Interface—client-side", 880, 188),
)

PARTS: Tuple[Part, ...] = (
    Part(
        "sources",
        "Encyclopedic sources",
        "Article prose, images and place names are fetched from Wikipedia, "
        "Deutsche Biographie, Commons and Nominatim, and cached before any step "
        "reads them.",
        (8, 40, 168, 150),
        decor="sources",
        lines=("Article prose", "Images", "Place names"),
    ),
    Part(
        "inference",
        "Language model",
        "The interpretative decisions—which episodes constitute a life, which "
        "modern place a toponym denotes—are model calls, each returning a "
        "declared schema rather than free text.",
        (8, 214, 168, 150),
        decor="inference",
        metric="{pipeline.call_sites} call sites · {pipeline.schemas} schemas",
    ),
    Part(
        "person-pipeline",
        "Personal story pipeline",
        "One biography end to end. After sourcing it forks into a narrative, an "
        "imagery, a network and an identity branch, reconverging at review and "
        "translation.",
        (220, 40, 392, 124),
        decor="steps",
        lane="person",
        metric="{pipeline.person_steps} steps · {pipeline.person_layers} layers",
        lines=("narrative · imagery · network · identity",),
    ),
    Part(
        "meta-pipeline",
        "Meta story pipeline",
        "A theme across several finished biographies. A network branch and a map "
        "branch run independently and meet in the composition step.",
        (220, 180, 392, 124),
        decor="steps",
        lane="meta",
        metric="{pipeline.meta_steps} steps · {pipeline.meta_layers} layers",
        lines=("network branch · map branch · composition",),
    ),
    Part(
        "kinds",
        "Four kinds of step",
        "An inference call, deterministic code, a retrieval from an external "
        "service or an image generation—the classification partitions both "
        "pipelines by cost and by failure mode.",
        (220, 320, 392, 44),
        decor="kinds",
        frame="none",
    ),
    Part(
        "files",
        "Artifacts on disk",
        "Denormalised JSON documents in a directory tree. The two halves of the "
        "system communicate through these and through nothing else: no database, "
        "no server.",
        (656, 40, 180, 324),
        decor="frame",
        frame="soft",
        metric="{pipeline.artifacts} declared files",
    ),
    Part(
        "registry",
        "persons.json",
        "The identity and portrait of each subject, in one-to-one correspondence "
        "with the per-person directories that hold everything else.",
        (668, 88, 156, 54),
        decor="file",
        parent="files",
        lines=("identity, portrait",),
    ),
    Part(
        "events",
        "life_events.json",
        "The narrative spine: dated events with places, persons, sources, images "
        "and a typed icon, grouped into the chapters of a life.",
        (668, 152, 156, 70),
        decor="file",
        parent="files",
        lines=("dated events", "chapters, sources"),
    ),
    Part(
        "ego-network",
        "ego_network.json",
        "The subject's relationships as typed, weighted and dated edges, "
        "generated independently of the narrative.",
        (668, 232, 156, 54),
        decor="file",
        parent="files",
        lines=("typed, weighted edges",),
    ),
    Part(
        "meta-story",
        "meta_story.json",
        "A second-order artifact: a theme across several biographies, and the "
        "only family whose inputs are other artifacts of this system.",
        (668, 296, 156, 54),
        decor="file",
        parent="files",
        lines=("a theme across lives",),
    ),
    Part(
        "slides",
        "Person story",
        "Full-screen, scroll-snapped slides—overview, chapter, event, "
        "conclusion—advanced one unit at a time, every position a citable "
        "address.",
        (880, 40, 188, 168),
        decor="slides",
        lines=("overview, chapters, events, conclusion",),
    ),
    Part(
        "sections",
        "Meta story",
        "A continuous document advanced by scrolling, whose visual sections pin "
        "a component while narration cards scroll over it.",
        (880, 222, 188, 142),
        decor="sections",
        lines=("component pinned, narration scrolls",),
    ),
    Part(
        "prose",
        "Narrative text",
        "The event's own description, and in a meta story the article prose that "
        "supplies the context around what the components encode.",
        (8, 396, 256, 140),
        decor="prose",
        lines=("the event's own description",),
    ),
    Part(
        "timeline",
        "Timeline",
        "Every event at its position in the life, banded by chapter. In a "
        "person's story it doubles as the navigation control.",
        (276, 396, 256, 140),
        decor="timeline",
        lines=("chapters banded, events placed",),
    ),
    Part(
        "map",
        "Map",
        "The events whose places resolved to coordinates, on a label-free "
        "basemap whose camera follows the reader rather than the reader panning "
        "it.",
        (544, 396, 256, 140),
        decor="map",
        lines=("places resolved to coordinates",),
    ),
    Part(
        "graph",
        "Social network",
        "The documented relationships as a force-directed graph, typed and "
        "weighted exactly as the artifact records them.",
        (812, 396, 256, 140),
        decor="graph",
        lines=("typed, weighted relationships",),
    ),
)

LINKS: Tuple[Link, ...] = (
    Link("sources", "person-pipeline", label="material", source_at=0.5, jog=0.35),
    Link("inference", "person-pipeline", kind="call", source_at=0.35, jog=0.78),
    Link("inference", "meta-pipeline", kind="call", source_at=0.65, jog=0.56),
    Link("person-pipeline", "files", label="writes", target_at=0.3, jog=0.5),
    Link(
        "meta-pipeline",
        "files",
        label="reads · writes",
        both=True,
        target_at=0.72,
        jog=0.5,
    ),
    Link("files", "slides", label="loads", source_at=0.25, jog=0.5),
    Link("files", "sections", source_at=0.8, jog=0.32),
)

BUS = Bus(
    source="events",
    targets=("prose", "timeline", "map", "graph"),
    label="one event record, four encodings",
    drop_x=858,
    rail_y=382,
    label_x=272,
)

CAPTION_TITLE = "The system end to end"
CAPTION_SUB = (
    "Encyclopedic sources and model inference on the left feed the two "
    "generation pipelines, which write the artifacts the interface on the "
    "right reads. The foot shows the four encodings a single event record is "
    "presented in."
)


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def part_ids() -> List[str]:
    return [part.id for part in PARTS]


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
        "caption": {"title": CAPTION_TITLE, "sub": CAPTION_SUB},
        "stages": [stage.to_json() for stage in STAGES],
        "parts": [part.to_json() for part in PARTS],
        "links": [link.to_json() for link in LINKS],
        "bus": BUS.to_json(),
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
    for end in (BUS.source, *BUS.targets):
        if end not in known:
            problems.append(SceneProblem("teaser", f"bus names unknown part '{end}'"))

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
