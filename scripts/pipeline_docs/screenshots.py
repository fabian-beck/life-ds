#!/usr/bin/env python3
"""Screenshots of the running application, declared in the report and captured
from a browser.

The report documents an interface, and an interface has to be shown. Everything
else on the page is derived from the source at build time, so a picture pasted
in by hand would be the one claim in the document nobody could re-derive: it
would age silently, and no reader could tell when.

A screenshot is therefore **described** rather than deposited. `report.md`
declares where in the application the picture is taken—the route, the viewport,
what to wait for, which region to clip—and the picture itself is a build
artifact produced from that description by driving a real browser:

    python scripts/generate_report.py --shots        # missing and stale ones
    python scripts/generate_report.py --shots all    # every declared shot

The description is the source; the picture beside it is output. That is what
makes the figures regeneratable: the application changes, the command is re-run,
and every screenshot in the report is retaken from the same declared positions.

Capture is deliberately not part of an ordinary build. It needs a browser and a
dev server, while the rest of the build needs neither—`--check` must stay
runnable anywhere. A build therefore embeds what is on disk and *says* what is
missing or stale rather than quietly taking a new picture.

**Staleness is a property of the description, not of the application.** Each
capture records the fingerprint of the spec it was taken from, so moving a shot
to another route or resizing its viewport marks it stale, while rewording its
caption does not. Whether the application itself has changed under an unchanged
description is not knowable from here; that is what `--shots all` is for.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS_DIR = REPO_ROOT / "docs" / "report" / "screenshots"
INDEX_NAME = "captures.json"
CAPTURE_SCRIPT = REPO_ROOT / "scripts" / "capture_report_screenshots.mjs"

FORMATS = ("png", "jpeg")
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 820
# Twice the CSS size, so a figure holds up on paper as well as on screen, and
# JPEG rather than PNG because the pictures are inlined into a single-file
# report: the landing page alone is 2.3 MB as a lossless capture at this scale
# and 0.5 MB as a high-quality JPEG, and no reader can tell them apart. A shot
# whose subject is a hairline or a screenful of small type can ask for
# `format=png` and pay for it.
DEFAULT_SCALE = 2
DEFAULT_FORMAT = "jpeg"
DEFAULT_QUALITY = 88

# Recapture selectors accepted by `--shots`.
STALE = "stale"
ALL = "all"


class ScreenshotError(ValueError):
    """A `::: screenshot` block that does not describe a capture."""


@dataclass(frozen=True)
class Shot:
    """One declared screenshot: where the picture is taken, and of what.

    Only the fields above `caption` describe the picture. `caption` and `alt`
    describe what is said about it, which is why they stay out of the
    fingerprint—prose is edited far more often than a viewport is, and an
    editorial pass must not report every figure as stale.
    """

    id: str
    route: str
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    scale: int = DEFAULT_SCALE
    clip: Optional[Tuple[int, int, int, int]] = None
    wait: str = ""
    anchor: str = ""
    settle: int = 0
    scroll: int = 0
    format: str = DEFAULT_FORMAT
    quality: int = DEFAULT_QUALITY
    caption: str = ""
    alt: str = ""
    line: int = 0

    @property
    def file_name(self) -> str:
        return f"{self.id}.{'jpg' if self.format == 'jpeg' else 'png'}"

    @property
    def css_size(self) -> Tuple[int, int]:
        """The size of the picture in CSS pixels—the clip, or the viewport."""
        if self.clip:
            return self.clip[2], self.clip[3]
        return self.width, self.height

    def spec(self) -> Dict[str, Any]:
        """Everything that decides what the browser produces."""
        return {
            "id": self.id,
            "route": self.route,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
            "clip": list(self.clip) if self.clip else None,
            "wait": self.wait,
            "anchor": self.anchor,
            "settle": self.settle,
            "scroll": self.scroll,
            "format": self.format,
            "quality": self.quality if self.format == "jpeg" else None,
        }

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(self.spec(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def describe(self) -> str:
        """The declaration in one line, for the page and for the build log.

        Each part is named, because the line is printed under the figure where
        a reader meets it cold: `#/en/meta/computing_pioneers · 1280x820 · @2x`
        is three facts to anyone who already knows the shape of a route, a
        viewport and a device pixel ratio, and a string of noise to everyone
        else. Naming them costs a few words and spares the reader the guess.
        """
        width, height = self.css_size
        parts = [f"Address {self.route}", f"viewport {width}×{height}"]
        if self.scale != 1:
            parts.append(f"{self.scale}× density")
        if self.clip:
            parts.append("clipped to the region declared")
        return "  ·  ".join(parts)


@dataclass
class Capture:
    """What was actually written for a shot, the last time one was taken."""

    id: str
    file: str
    fingerprint: str
    captured: str
    bytes: int = 0
    css_width: int = 0
    css_height: int = 0
    scale: int = 1
    route: str = ""

    @classmethod
    def from_json(cls, shot_id: str, data: Dict[str, Any]) -> "Capture":
        return cls(
            id=shot_id,
            file=str(data.get("file", "")),
            fingerprint=str(data.get("fingerprint", "")),
            captured=str(data.get("captured", "")),
            bytes=int(data.get("bytes", 0) or 0),
            css_width=int(data.get("css_width", 0) or 0),
            css_height=int(data.get("css_height", 0) or 0),
            scale=int(data.get("scale", 1) or 1),
            route=str(data.get("route", "")),
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "fingerprint": self.fingerprint,
            "captured": self.captured,
            "bytes": self.bytes,
            "css_width": self.css_width,
            "css_height": self.css_height,
            "scale": self.scale,
            "route": self.route,
        }


@dataclass
class Album:
    """The declared shots and the captures on disk, paired up."""

    shots: List[Shot] = field(default_factory=list)
    captures: Dict[str, Capture] = field(default_factory=dict)
    directory: Path = SHOTS_DIR

    def status(self, shot: Shot) -> str:
        """`current`, `stale` (the description moved) or `missing`."""
        capture = self.captures.get(shot.id)
        if capture is None or not (self.directory / capture.file).is_file():
            return "missing"
        if capture.fingerprint != shot.fingerprint:
            return "stale"
        return "current"

    def select(self, selector: str) -> List[Shot]:
        """Which shots a `--shots` argument asks for."""
        if selector == ALL:
            return list(self.shots)
        if selector == STALE:
            return [shot for shot in self.shots if self.status(shot) != "current"]
        wanted = [name.strip() for name in selector.split(",") if name.strip()]
        known = {shot.id for shot in self.shots}
        unknown = [name for name in wanted if name not in known]
        if unknown:
            raise ScreenshotError(
                "no '::: screenshot' block declares "
                + ", ".join(sorted(unknown))
                + (
                    "—the report declares " + ", ".join(sorted(known))
                    if known
                    else "—the report declares none"
                )
            )
        return [shot for shot in self.shots if shot.id in wanted]


# ---------------------------------------------------------------------------
# Reading the declarations
# ---------------------------------------------------------------------------


def _int(params: Dict[str, str], key: str, fallback: int) -> int:
    raw = params.get(key)
    if raw is None or raw == "":
        return fallback
    try:
        return int(raw)
    except ValueError:
        raise ScreenshotError(f"{key}={raw!r} is not a whole number")


def parse(params: Dict[str, str], body: str = "", line: int = 0) -> Shot:
    """One `::: screenshot` block's arguments, checked and typed."""
    shot_id = (params.get("id") or "").strip()
    if not shot_id or not all(part.isalnum() for part in shot_id.split("-")):
        raise ScreenshotError(
            f"id={shot_id!r} is not usable as a file name—use letters, digits "
            "and hyphens"
        )

    route = (params.get("route") or "").strip()
    if not route:
        raise ScreenshotError("route is empty—say where in the application to look")

    clip: Optional[Tuple[int, int, int, int]] = None
    raw_clip = (params.get("clip") or "").strip()
    if raw_clip:
        pieces = [piece.strip() for piece in raw_clip.split(",")]
        if len(pieces) != 4 or not all(piece.lstrip("-").isdigit() for piece in pieces):
            raise ScreenshotError(
                f"clip={raw_clip!r} is not 'x,y,width,height' in CSS pixels"
            )
        numbers = [int(piece) for piece in pieces]
        if numbers[2] <= 0 or numbers[3] <= 0:
            raise ScreenshotError(f"clip={raw_clip!r} has no area")
        clip = (numbers[0], numbers[1], numbers[2], numbers[3])

    image_format = (params.get("format") or DEFAULT_FORMAT).strip().lower()
    if image_format not in FORMATS:
        raise ScreenshotError(
            f"format={image_format!r} is not one of " + ", ".join(FORMATS)
        )

    shot = Shot(
        id=shot_id,
        route=route,
        width=_int(params, "width", DEFAULT_WIDTH),
        height=_int(params, "height", DEFAULT_HEIGHT),
        scale=_int(params, "scale", DEFAULT_SCALE),
        clip=clip,
        wait=(params.get("wait") or "").strip(),
        anchor=(params.get("anchor") or "").strip(),
        settle=_int(params, "settle", 0),
        scroll=_int(params, "scroll", 0),
        format=image_format,
        quality=_int(params, "quality", DEFAULT_QUALITY),
        caption=(params.get("caption") or "").strip(),
        alt=(params.get("alt") or "").strip(),
        line=line,
    )
    if shot.width <= 0 or shot.height <= 0:
        raise ScreenshotError("width and height are the viewport, in CSS pixels")
    if shot.scale < 1 or shot.scale > 4:
        raise ScreenshotError(f"scale={shot.scale} is outside 1–4")
    if not shot.caption and not body.strip():
        raise ScreenshotError(
            "caption is empty—a figure needs a sentence saying what it shows"
        )
    if clip and (
        clip[0] + clip[2] > shot.width * 4 or clip[1] + clip[3] > shot.height * 8
    ):
        raise ScreenshotError(
            f"clip={raw_clip!r} reaches far outside a {shot.width}x{shot.height} page"
        )
    return shot


def load_index(directory: Path = SHOTS_DIR) -> Dict[str, Capture]:
    path = directory / INDEX_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    shots = data.get("shots")
    if not isinstance(shots, dict):
        return {}
    return {
        shot_id: Capture.from_json(shot_id, entry)
        for shot_id, entry in shots.items()
        if isinstance(entry, dict)
    }


def save_index(captures: Dict[str, Capture], directory: Path = SHOTS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / INDEX_NAME
    payload = {
        "note": (
            "Written by scripts/generate_report.py --shots. Each entry records "
            "the fingerprint of the '::: screenshot' declaration the picture "
            "was taken from, which is how a build knows a figure is stale."
        ),
        "shots": {
            shot_id: capture.to_json() for shot_id, capture in sorted(captures.items())
        },
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def collect(document: Any, directory: Path = SHOTS_DIR) -> Album:
    """Every `::: screenshot` in the compiled report, with what disk holds.

    Blocks that do not parse are skipped rather than raised on: `validate.py`
    reports them against their line number, and it has to be able to report all
    of them at once.
    """
    shots: List[Shot] = []
    seen: set = set()
    for mount in document.mounts:
        if mount.component != "screenshot":
            continue
        try:
            shot = parse(mount.params, mount.body_markdown, mount.line)
        except ScreenshotError:
            continue
        if shot.id in seen:
            continue
        seen.add(shot.id)
        shots.append(shot)
    return Album(shots, load_index(directory), directory)


# ---------------------------------------------------------------------------
# Into the page
# ---------------------------------------------------------------------------


def payload(album: Album) -> Dict[str, Dict[str, Any]]:
    """The screenshots as the page consumes them: one data URI per shot.

    Inlined, like everything else on this page. The report is one file that has
    to work from `file://` and out of an email attachment, so a figure that
    lived beside it as a separate PNG would be a figure that travels only
    sometimes.
    """
    embedded: Dict[str, Dict[str, Any]] = {}
    for shot in album.shots:
        status = album.status(shot)
        capture = album.captures.get(shot.id)
        width, height = shot.css_size
        entry: Dict[str, Any] = {
            "id": shot.id,
            "route": shot.route,
            "caption": shot.caption,
            "alt": shot.alt or shot.caption,
            "width": width,
            "height": height,
            "declaration": shot.describe(),
            "status": status,
            "captured": capture.captured if capture else "",
            "src": "",
        }
        if capture is not None and status != "missing":
            path = album.directory / capture.file
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            entry["src"] = f"data:{mime};base64,{data}"
            entry["bytes"] = capture.bytes or path.stat().st_size
        embedded[shot.id] = entry
    return embedded


# ---------------------------------------------------------------------------
# Taking the pictures
# ---------------------------------------------------------------------------


def manifest(shots: Sequence[Shot], directory: Path = SHOTS_DIR) -> Dict[str, Any]:
    """What the browser driver needs, and nothing about the report."""
    return {
        "outDir": str(directory),
        "shots": [dict(shot.spec(), file=shot.file_name) for shot in shots],
    }


def capture(
    shots: Sequence[Shot],
    directory: Path = SHOTS_DIR,
    base_url: Optional[str] = None,
    timeout: int = 600,
    verbose: bool = False,
) -> Tuple[Dict[str, Capture], List[str]]:
    """Drive the browser over the declared shots; return captures and failures.

    The driving itself is Node's: the application is a Vite app and the
    repository already carries Playwright for its interface tests, so a second
    browser stack in Python would be a second thing to install and pin. This
    side owns the description and the bookkeeping—what a shot is, whether it is
    stale, what the page embeds—and hands the browser a manifest that says
    nothing about the report.
    """
    directory.mkdir(parents=True, exist_ok=True)
    captures = load_index(directory)
    if not shots:
        return captures, []

    with tempfile.TemporaryDirectory() as workspace:
        manifest_path = Path(workspace) / "shots.json"
        results_path = Path(workspace) / "results.json"
        manifest_path.write_text(
            json.dumps(manifest(shots, directory), indent=2), encoding="utf-8"
        )
        command = [
            _node(),
            str(CAPTURE_SCRIPT),
            "--manifest",
            str(manifest_path),
            "--results",
            str(results_path),
        ]
        if base_url:
            command += ["--base-url", base_url]
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
            raise ScreenshotError(
                "node was not found—the capture step drives Playwright through "
                f"{CAPTURE_SCRIPT.relative_to(REPO_ROOT).as_posix()}"
            )
        except subprocess.TimeoutExpired:
            raise ScreenshotError(
                f"capturing did not finish within {timeout}s—run "
                f"'node {CAPTURE_SCRIPT.relative_to(REPO_ROOT).as_posix()}' "
                "directly to see where it stops"
            )
        if completed.returncode != 0 and not results_path.is_file():
            output = (completed.stdout or "").strip()
            raise ScreenshotError(
                "the capture step failed"
                + (f":\n{_indent(output)}" if output else " with no output")
            )
        if not verbose and completed.stdout:
            print(_indent(completed.stdout.strip()))

        results = json.loads(results_path.read_text(encoding="utf-8"))

    by_id = {shot.id: shot for shot in shots}
    failures: List[str] = []
    for result in results.get("shots", []):
        shot = by_id.get(result.get("id", ""))
        if shot is None:
            continue
        if result.get("error"):
            failures.append(f"{shot.id}: {result['error']}")
            continue
        width, height = shot.css_size
        captures[shot.id] = Capture(
            id=shot.id,
            file=shot.file_name,
            fingerprint=shot.fingerprint,
            captured=str(result.get("captured", "")),
            bytes=int(result.get("bytes", 0) or 0),
            css_width=width,
            css_height=height,
            scale=shot.scale,
            route=shot.route,
        )
    save_index(captures, directory)
    return captures, failures


def prune(album: Album) -> List[str]:
    """Captures whose declaration is gone from the report, by file name."""
    declared = {shot.id for shot in album.shots}
    return sorted(
        capture.file
        for shot_id, capture in album.captures.items()
        if shot_id not in declared
    )


def _node() -> str:
    return os.environ.get("NODE", "node")


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" for line in text.splitlines())
