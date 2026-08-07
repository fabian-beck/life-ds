#!/usr/bin/env python3
"""Emit the standalone HTML report.

Everything is inlined—CSS, JS, the compiled Markdown and the payload—so the
file works from `file://`, from a repo checkout, or attached to an email, with no
build step and no network access.

The shell here is deliberately thin: a title block, a contents rail, the compiled
report body, and a colophon. It holds no content of its own. Prose comes from
`docs/report/report.md`; every number, table and figure comes from the payload
and is written into the body's mount points by `app.js`. Adding a section to the
report therefore means editing the Markdown, never this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .report import Document

ASSETS = Path(__file__).resolve().parent / "assets"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<meta name="description" content="__DESCRIPTION__">
<style>
__CSS__
</style>
</head>
<body>
<a class="skip" href="#report">Skip to the report</a>

<!-- The state of the document, stated before the document: this report is
     drafted alongside the system it describes, and a reader who lands on it
     from a link has no other way to know that. It is markup rather than prose
     in `report.md` so that it precedes the title block on screen and on paper
     alike, and so that removing it when the report is finished is one edit. -->
<div class="draftbanner" role="note" aria-label="Document status">
  <p class="draftbanner-tag">Draft</p>
  <p class="draftbanner-text">
    <strong>Preliminary version—work in progress.</strong> This report is
    written alongside the system it describes. Its prose, figures, and
    measurements are incomplete and under active revision, and any part of it
    may change or be withdrawn.
  </p>
</div>

<div class="shell">
  <!-- The contents rail is a sibling of the report, not part of it: the report
       body is compiled from Markdown and must not have to know about chrome. -->
  <aside class="rail" id="rail" aria-label="Report navigation">
    <p class="rail-title">Contents</p>
    <nav class="rail-nav" id="rail-nav"></nav>
    <div class="rail-foot" id="rail-foot"></div>
  </aside>

  <main class="page">
    <header class="titleblock">
      <p class="kicker">Technical report</p>
      <h1>__H1__</h1>
      <p class="subtitle">__SUBTITLE__</p>
__AUTHORS__
      <div class="meta-row" id="meta-row"></div>
      <div class="abstract">
        <p class="abstract-label">Abstract</p>
        __ABSTRACT__
      </div>
    </header>

    <div class="report" id="report">
__BODY__
    </div>

    <footer class="colophon">
      <p>
        Authored prose lives in <code>__SOURCE__</code>. Every figure, table,
        count and prompt in this report is computed at build time by
        <code>scripts/generate_report.py</code>—from the abstract syntax trees
        of <code>scripts/</code> and from the repository itself. Step
        explanations are written by a language model from the source and cached
        against a fingerprint of it. Nothing here is transcribed by hand except
        the prose.
      </p>
      <p id="colophon-build"></p>
    </footer>
  </main>
</div>

<!-- Below the rail breakpoint the contents section is ordinary document content,
     so it scrolls away and never comes back. This button brings it back on
     demand, without pinning a column the narrow measure cannot spare. Chrome,
     like the rail: `app.js` fills the panel from the contents already on the
     page, and a reader without JavaScript still has that section. -->
<button class="toc-fab" id="toc-fab" type="button" aria-controls="toc-pop" aria-expanded="false" hidden>
  <span class="toc-fab-mark" aria-hidden="true"></span>Contents
</button>
<nav class="toc-pop" id="toc-pop" aria-label="Contents" hidden></nav>

<aside class="drawer" id="drawer" aria-label="Step details">
  <div class="drawer-head">
    <h2 id="drawer-title">Step</h2>
    <button class="drawer-close" id="drawer-close" type="button" aria-label="Close details">&times;</button>
  </div>
  <div class="drawer-body" id="drawer-body"></div>
</aside>

<!-- Where the pipeline figures keep the detail the compact drawing gives up on
     a narrow display: the full chart, over the whole viewport, built by app.js
     when the reader asks for it and torn down when they close it. -->
<div class="chart-modal" id="chart-modal" role="dialog" aria-modal="true" aria-labelledby="chart-modal-title" aria-hidden="true">
  <div class="chart-modal-panel">
    <div class="chart-modal-head">
      <h2 id="chart-modal-title">Pipeline</h2>
      <button class="drawer-close" id="chart-modal-close" type="button" aria-label="Close the full chart">&times;</button>
    </div>
    <div class="chart-modal-body" id="chart-modal-body"></div>
  </div>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
window.PIPELINE = JSON.parse(document.getElementById("payload").textContent);
</script>
<script>
__JS__
</script>
</body>
</html>
"""

FALLBACK_ABSTRACT = "<p>No abstract was written in the report's front matter.</p>"

# The ORCID mark, drawn in ink rather than in the organization's green: the page
# spends color on the step kinds alone, and an author's identifier is not one of
# them. The disc takes `currentColor`, the letterforms are knocked out of it.
ORCID_MARK = (
    '<svg class="orcid-mark" viewBox="0 0 256 256" aria-hidden="true"'
    ' focusable="false">'
    '<circle cx="128" cy="128" r="128" fill="currentColor"/>'
    '<path fill="var(--paper)" d="M86.3 186.2H70.9V79.1h15.4v107.1z"/>'
    '<path fill="var(--paper)" d="M108.9 79.1h41.6c39.6 0 57 28.3 57 53.6 0'
    " 27.5-21.5 53.6-56.8 53.6h-41.8V79.1zm15.4 93.3h24.5c34.9 0 42.9-26.5"
    ' 42.9-39.7 0-21.5-13.7-39.7-43.7-39.7h-23.7v79.4z"/>'
    '<path fill="var(--paper)" d="M88.7 56.8c0 5.5-4.5 10.1-10.1 10.1-5.6'
    ' 0-10.1-4.6-10.1-10.1 0-5.6 4.5-10.1 10.1-10.1 5.6 0 10.1 4.6 10.1 10.1z"/>'
    "</svg>"
)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _abstract_html(document: Document) -> str:
    text = document.front.get("abstract", "").strip()
    if not text:
        return FALLBACK_ABSTRACT
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "\n".join(f"<p>{_escape(part)}</p>" for part in paragraphs)


def _authors_html(document: Optional[Document]) -> str:
    """The byline, written into the page rather than hydrated into it.

    Authorship is authored, not measured, so it belongs to the served HTML: it
    has to be there for a reader without JavaScript, for a printer, and for
    whatever reads the page as a document.
    """
    authors = document.authors if document else []
    if not authors:
        return ""

    items = []
    for author in authors:
        name = _escape(author.name)
        if author.url:
            head = f'<a class="author-name" href="{_escape(author.url)}">{name}</a>'
        else:
            head = f'<span class="author-name">{name}</span>'
        if author.orcid:
            head += (
                f'<a class="orcid" href="{_escape(author.orcid_url)}"'
                f' data-orcid="{_escape(author.orcid)}"'
                f' aria-label="ORCID iD for {name}">{ORCID_MARK}</a>'
            )
        if author.affiliation:
            head += f'<span class="author-affil">{_escape(author.affiliation)}</span>'
        items.append(f'        <li class="author">{head}</li>')
    return '      <ul class="authors">\n' + "\n".join(items) + "\n      </ul>"


def render(payload: Dict[str, Any], document: Optional[Document] = None) -> str:
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    # `</script>` inside the payload would close the tag early; escaping the
    # slash keeps the JSON valid while making that impossible.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    title = document.title if document else "Life Data Stories—technical report"
    subtitle = (document.front.get("subtitle", "") if document else "").strip()
    description = (
        (document.front.get("description", "").strip() if document else "")
        or subtitle
        or "Technical report on the Life Data Stories system."
    )
    body = document.html if document else "<p>No report source was compiled.</p>"
    source = document.source_path if document else "docs/report/report.md"
    abstract = _abstract_html(document) if document else FALLBACK_ABSTRACT

    return (
        TEMPLATE.replace("__CSS__", css)
        .replace("__JS__", script)
        .replace("__BODY__", body)
        .replace("__ABSTRACT__", abstract)
        .replace("__TITLE__", _escape(title))
        .replace("__H1__", _escape(title))
        .replace("__SUBTITLE__", _escape(subtitle))
        .replace("__AUTHORS__", _authors_html(document))
        .replace("__DESCRIPTION__", _escape(description))
        .replace("__SOURCE__", _escape(source))
        .replace("__DATA__", data)
    )


def write(
    payload: Dict[str, Any], path: Path, document: Optional[Document] = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit LF: the repository stores this file text-normalized (see
    # .gitattributes), so writing CRLF on Windows would show the whole page as
    # changed on every rebuild from a Windows machine.
    path.write_text(render(payload, document), encoding="utf-8", newline="\n")
    return path
