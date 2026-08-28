#!/usr/bin/env python3
"""Render a merged fact-checking round as one self-contained HTML page.

No external stylesheet, script, or font: the report is opened from disk, mailed
around, and archived next to the bundle it describes, and any of those breaks a
page that fetches something.

The verdict scale is a status scale, not a series palette, so it is drawn in the
four fixed status colors in their own order — supported, partly supported,
unsupported, contradicted — and the three verdicts that judge the extraction
rather than the story take neutral ink steps. Every segment carries its label
and count in the legend and again in a table, so nothing is encoded in color
alone, which is what the two sub-3:1 status colors require.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .models import (
    EVIDENCE_QUALITY_LABELS,
    SEVERITY_LABELS,
    VERDICT_LABELS,
)

# Status palette for the four verdicts about the story, neutral ink steps for
# the three about the evaluation itself, and one more for a contested fact.
VERDICT_COLORS = {
    "supported": ("#0ca30c", "#0ca30c"),
    "partly_supported": ("#fab219", "#fab219"),
    "unsupported": ("#ec835a", "#ec835a"),
    "contradicted": ("#d03b3b", "#d03b3b"),
    "not_a_claim": ("#c3c2b7", "#52514e"),
    "misextracted": ("#898781", "#898781"),
    "unclear": ("#52514e", "#c3c2b7"),
    "contested": ("#2a78d6", "#3987e5"),
}

VERDICT_ORDER = (
    "supported",
    "partly_supported",
    "unsupported",
    "contradicted",
    "not_a_claim",
    "misextracted",
    "unclear",
    "contested",
)

ALL_VERDICT_LABELS = dict(VERDICT_LABELS)
ALL_VERDICT_LABELS["contested"] = "Contested (tied)"


def _verdict_variables(mode: int) -> str:
    """The verdict colors as custom properties, light or dark column."""
    return "\n".join(
        f"  --v-{key}: {values[mode]};" for key, values in VERDICT_COLORS.items()
    )


CSS_TEMPLATE = """
:root {
  color-scheme: light dark;
__LIGHT_VERDICTS__
  --surface: #fcfcfb;
  --plane: #f9f9f7;
  --ink: #0b0b0b;
  --ink-2: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11, 11, 11, 0.1);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
__DARK_VERDICTS__
    --surface: #1a1a19;
    --plane: #0d0d0d;
    --ink: #ffffff;
    --ink-2: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255, 255, 255, 0.1);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--plane);
  color: var(--ink);
  line-height: 1.55;
  font-size: 15px;
}
main { max-width: 1120px; margin: 0 auto; padding: 32px 24px 80px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 34px 0 10px; }
h3 { font-size: 15px; margin: 22px 0 8px; color: var(--ink-2); }
p { margin: 0 0 12px; max-width: 76ch; }
.lede { color: var(--ink-2); }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 18px;
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; }
.tile .value { font-size: 30px; line-height: 1.1; font-weight: 640; }
.tile .label { color: var(--ink-2); font-size: 13px; margin-top: 4px; }
.tile .sub { color: var(--muted); font-size: 12px; }
.bar { display: flex; gap: 2px; height: 22px; margin: 6px 0; }
.bar .seg:first-child { border-radius: 4px 0 0 4px; }
.bar .seg:last-child { border-radius: 0 4px 4px 0; }
.bar .seg:only-child { border-radius: 4px; }
.seg { min-width: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; margin: 8px 0 2px; font-size: 13px; color: var(--ink-2); }
.legend span.key { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }
.multiples { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 4px 28px; }
.multiple { padding: 6px 0; }
.multiple .head { display: flex; justify-content: space-between; font-size: 13px; color: var(--ink-2); }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; margin: 8px 0 4px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.pill { display: inline-block; border-radius: 999px; padding: 1px 9px; font-size: 12px; border: 1px solid var(--axis); color: var(--ink-2); white-space: nowrap; }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; margin-right: 5px; }
blockquote { margin: 4px 0; padding-left: 10px; border-left: 3px solid var(--axis); color: var(--ink-2); }
.claim { font-weight: 560; }
footer { color: var(--muted); font-size: 12.5px; border-top: 1px solid var(--grid); margin-top: 40px; padding-top: 14px; }
code { background: var(--grid); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
"""

CSS = CSS_TEMPLATE.replace("__LIGHT_VERDICTS__", _verdict_variables(0)).replace(
    "__DARK_VERDICTS__", _verdict_variables(1)
)


def _plural(count: int, singular: str, plural: Optional[str] = None) -> str:
    """A count with its noun, so headings do not read "1 people"."""
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def percent(part: float, whole: float) -> str:
    if not whole:
        return "—"
    return f"{100 * part / whole:.0f}%"


def color_of(verdict: str) -> str:
    """The custom property a verdict is drawn in, so dark mode swaps with it."""
    if verdict not in VERDICT_COLORS:
        return "var(--muted)"
    return f"var(--v-{verdict})"


def swatch(verdict: str) -> str:
    return f'<span class="swatch" style="background:{color_of(verdict)}"></span>'


def stacked_bar(counts: Mapping[str, int], order: Sequence[str] = VERDICT_ORDER) -> str:
    """One horizontal bar, segments in the fixed verdict order."""
    total = sum(counts.get(key, 0) for key in order)
    if total == 0:
        return '<p class="lede">No judgments.</p>'
    segments = []
    for key in order:
        value = counts.get(key, 0)
        if not value:
            continue
        share = 100 * value / total
        segments.append(
            f'<div class="seg" style="width:{share:.4f}%;background:{color_of(key)}" '
            f'title="{esc(ALL_VERDICT_LABELS.get(key, key))}: {value}"></div>'
        )
    return f'<div class="bar">{"".join(segments)}</div>'


def legend(counts: Mapping[str, int], order: Sequence[str] = VERDICT_ORDER) -> str:
    total = sum(counts.get(key, 0) for key in order)
    keys = []
    for key in order:
        value = counts.get(key, 0)
        if not value:
            continue
        keys.append(
            f'<span class="key">{swatch(key)}'
            f"{esc(ALL_VERDICT_LABELS.get(key, key))} "
            f"<b>{value}</b> ({percent(value, total)})</span>"
        )
    return f'<div class="legend">{"".join(keys)}</div>'


def small_multiples(groups: Sequence[Tuple[str, Mapping[str, int]]]) -> str:
    """One bar per group, all on the same 0–100% scale."""
    blocks = []
    for name, counts in groups:
        total = sum(counts.values())
        blocks.append(
            f'<div class="multiple"><div class="head"><span>{esc(name)}</span>'
            f"<span>{total}</span></div>{stacked_bar(counts)}</div>"
        )
    return f'<div class="multiples">{"".join(blocks)}</div>'


def table(
    headers: Sequence[str], rows: Sequence[Sequence[str]], numeric: Sequence[int] = ()
) -> str:
    head = "".join(
        (
            f'<th class="num">{esc(header)}</th>'
            if index in numeric
            else f"<th>{esc(header)}</th>"
        )
        for index, header in enumerate(headers)
    )
    body = []
    for row in rows:
        cells = "".join(
            f'<td class="num">{cell}</td>' if index in numeric else f"<td>{cell}</td>"
            for index, cell in enumerate(row)
        )
        body.append(f"<tr>{cells}</tr>")
    return (
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def verdict_pill(verdict: Optional[str]) -> str:
    if not verdict:
        return '<span class="pill">not judged</span>'
    return (
        f'<span class="pill"><span class="dot" '
        f'style="background:{color_of(verdict)}"></span>'
        f"{esc(ALL_VERDICT_LABELS.get(verdict, verdict))}</span>"
    )


def _tile(value: str, label: str, sub: str = "") -> str:
    return (
        f'<div class="tile"><div class="value">{esc(value)}</div>'
        f'<div class="label">{esc(label)}</div>'
        f'<div class="sub">{esc(sub)}</div></div>'
    )


def render(summary: Dict[str, Any]) -> str:
    """The whole report as one HTML document."""
    bundle = summary["bundle"]
    coverage = summary["coverage"]
    verdicts = summary["verdicts"]
    agreement = summary["agreement"]
    evidence = summary["evidence"]

    parts: List[str] = []
    parts.append(
        f"<h1>Fact check: {esc(bundle.get('name'))}</h1>"
        f'<p class="lede">'
        f"{coverage['facts']} sampled claims from "
        f"{_plural(len(bundle.get('persons') or {}), 'person story', 'person stories')}"
        f", judged by {_plural(len(summary['evaluators']), 'evaluator')}. "
        f"Bundle <code>{esc(bundle.get('bundle_id'))}</code>, seed "
        f"{esc(bundle.get('seed'))}, drawn from "
        f"{(bundle.get('population') or {}).get('facts_total', '—')} extracted claims."
        f"</p>"
    )

    supported = verdicts["consensus"].get("supported", 0)
    resolved = summary["resolved_count"]
    problems = summary["problem_count"]
    parts.append(
        '<div class="tiles">'
        + _tile(
            percent(supported, resolved),
            "Claims the sources support",
            f"{supported} of {resolved} with a settled verdict",
        )
        + _tile(
            percent(problems, resolved),
            "Claims with something wrong",
            "partly supported, unsupported, or contradicted",
        )
        + _tile(
            str(verdicts["consensus"].get("contradicted", 0)),
            "Contradicted by the sources",
            "the sources state something incompatible",
        )
        + _tile(
            percent(evidence["quotes_verified"], evidence["quotes_total"]),
            "Quotes found in the sources",
            f"{evidence['quotes_verified']} of {evidence['quotes_total']} quotes verbatim",
        )
        + _tile(
            (
                f"{agreement['pairwise']:.0%}"
                if agreement["pairwise"] is not None
                else "—"
            ),
            "Pairwise agreement",
            (
                f"Krippendorff α {agreement['alpha_full']:.2f}"
                if agreement["alpha_full"] is not None
                else "one evaluator only"
            ),
        )
        + "</div>"
    )

    parts.append("<h2>Verdicts</h2>")
    parts.append(
        '<div class="card">'
        + stacked_bar(verdicts["consensus"])
        + legend(verdicts["consensus"])
        + '<p class="lede">One verdict per claim: the majority of the evaluators '
        "who judged it, or <em>contested</em> where they tied.</p>" + "</div>"
    )

    for title, key in (
        ("By person", "by_person"),
        ("By part of the story", "by_scope"),
        ("By kind of claim", "by_claim_type"),
    ):
        groups = summary["verdicts"][key]
        if not groups:
            continue
        parts.append(f"<h3>{esc(title)}</h3>")
        parts.append(
            '<div class="card">'
            + small_multiples(
                sorted(groups.items(), key=lambda pair: -sum(pair[1].values()))
            )
            + "</div>"
        )

    parts.append("<h2>What the evidence search delivered</h2>")
    parts.append(
        "<p>Stage two searched the same cached materials the story was generated "
        "from, and every quote it returned was looked for in the source text "
        "afterwards. A quote that is not there is a fabrication, and it is "
        "counted here rather than dropped.</p>"
    )
    status_rows = [
        [
            esc(status),
            str(count),
            percent(count, coverage["facts"]),
        ]
        for status, count in sorted(
            evidence["status_counts"].items(), key=lambda pair: -pair[1]
        )
    ]
    parts.append(
        '<div class="card">'
        + table(["Search reported", "Claims", "Share"], status_rows, numeric=(1, 2))
        + "</div>"
    )

    if evidence["status_vs_verdict"]:
        rows = []
        verdict_keys = [key for key in VERDICT_ORDER if key in verdicts["consensus"]]
        for status, counts in sorted(evidence["status_vs_verdict"].items()):
            rows.append(
                [esc(status)] + [str(counts.get(key, 0)) for key in verdict_keys]
            )
        parts.append("<h3>Search result against the evaluators' verdict</h3>")
        parts.append(
            '<div class="card">'
            + table(
                ["Search reported"]
                + [ALL_VERDICT_LABELS.get(key, key) for key in verdict_keys],
                rows,
                numeric=tuple(range(1, len(verdict_keys) + 1)),
            )
            + '<p class="lede">Rows where the search reported evidence and the '
            "evaluators did not agree are where stage two is weakest.</p>" + "</div>"
        )

    if evidence["quality_counts"]:
        rows = [
            [esc(EVIDENCE_QUALITY_LABELS.get(key, key)), str(value)]
            for key, value in sorted(
                evidence["quality_counts"].items(), key=lambda pair: -pair[1]
            )
        ]
        parts.append("<h3>How the evaluators rated the quotes</h3>")
        parts.append(
            '<div class="card">'
            + table(["Rating", "Judgments"], rows, numeric=(1,))
            + "</div>"
        )

    parts.append("<h2>Agreement between evaluators</h2>")
    if len(summary["evaluators"]) < 2:
        parts.append(
            "<p>Only one evaluator submitted results, so there is nothing to compare.</p>"
        )
    else:
        alpha_full = agreement["alpha_full"]
        alpha_problem = agreement["alpha_problem"]
        parts.append(
            "<p>Percent agreement counts how often two evaluators picked the same "
            "verdict. Krippendorff's α discounts the agreement that the verdict "
            "distribution would produce by chance; the second α asks only whether "
            "they agreed that something was wrong.</p>"
        )
        rows = [
            [
                f"{esc(pair['first'])} vs {esc(pair['second'])}",
                str(pair["compared"]),
                f"{pair['agreed'] / pair['compared']:.0%}" if pair["compared"] else "—",
            ]
            for pair in agreement["pairs"]
        ]
        parts.append(
            '<div class="card">'
            + '<div class="tiles">'
            + _tile(
                f"{alpha_full:.2f}" if alpha_full is not None else "—",
                "α, seven-way scale",
            )
            + _tile(
                f"{alpha_problem:.2f}" if alpha_problem is not None else "—",
                "α, sound vs problem",
            )
            + _tile(str(len(summary["disagreements"])), "Claims judged differently")
            + "</div>"
            + table(["Pair", "Claims both judged", "Agreement"], rows, numeric=(1, 2))
            + "</div>"
        )

        if summary["disagreements"]:
            rows = []
            for entry in summary["disagreements"]:
                rows.append(
                    [
                        f'<span class="claim">{esc(entry["claim"])}</span>',
                        esc(entry["person"]),
                        " ".join(
                            f'<span class="pill">{esc(name)}: '
                            f"{esc(ALL_VERDICT_LABELS.get(verdict, verdict))}</span>"
                            for name, verdict in sorted(entry["verdicts"].items())
                        ),
                    ]
                )
            parts.append("<h3>Where they disagreed</h3>")
            parts.append(
                '<div class="card">'
                + table(["Claim", "Person", "Verdicts"], rows)
                + "</div>"
            )

    problem_rows = []
    for entry in summary["problems"]:
        quotes = "".join(
            f"<blockquote>{esc(quote['quote'])}<br /><span class=\"pill\">"
            f"{esc(quote['stance'])} · {esc(quote.get('title') or quote['material_id'])}"
            f"</span></blockquote>"
            for quote in entry["quotes"][:2]
        )
        notes = " ".join(entry["notes"])
        problem_rows.append(
            [
                f'<span class="claim">{esc(entry["claim"])}</span><br />'
                f'<span class="pill">{esc(entry["claim_type"])}</span> '
                f'<span class="pill">{esc(entry["unit_label"])}</span>'
                + (f"<br />{quotes}" if quotes else ""),
                esc(entry["person"]),
                verdict_pill(entry["verdict"])
                + (
                    f'<br /><span class="pill">{esc(SEVERITY_LABELS.get(entry["severity"], entry["severity"]))}</span>'
                    if entry.get("severity")
                    else ""
                ),
                esc(notes),
            ]
        )
    parts.append("<h2>Claims the round flagged</h2>")
    if problem_rows:
        parts.append(
            '<div class="card">'
            + table(
                ["Claim and evidence", "Person", "Verdict", "Evaluator notes"],
                problem_rows,
            )
            + "</div>"
        )
    else:
        parts.append(
            "<p>No claim was judged partly supported, unsupported, or "
            "contradicted, and none was contested.</p>"
        )

    parts.append("<h2>Every claim in the round</h2>")
    all_rows = []
    for entry in summary["facts"]:
        all_rows.append(
            [
                f'<span class="claim">{esc(entry["claim"])}</span>',
                esc(entry["person"]),
                esc(entry["unit_label"]),
                esc(entry["evidence_status"]),
                verdict_pill(entry["verdict"]),
                " ".join(
                    f'<span class="pill">{esc(name)}: '
                    f"{esc(ALL_VERDICT_LABELS.get(verdict, verdict))}</span>"
                    for name, verdict in sorted(entry["verdicts"].items())
                ),
            ]
        )
    parts.append(
        '<div class="card">'
        + table(
            ["Claim", "Person", "Section", "Search", "Consensus", "Per evaluator"],
            all_rows,
        )
        + "</div>"
    )

    evaluator_rows = [
        [
            esc(entry["name"]),
            str(entry["judged"]),
            percent(entry["judged"], coverage["facts"]),
            f"{entry['median_seconds']:.0f} s" if entry["median_seconds"] else "—",
            esc(entry["updated"] or ""),
        ]
        for entry in summary["evaluators"]
    ]
    parts.append("<h2>How the round was run</h2>")
    side_tables = table(
        [
            "Evaluator",
            "Claims judged",
            "Coverage",
            "Median time per claim",
            "Last saved",
        ],
        evaluator_rows,
        numeric=(1, 2, 3),
    )
    if summary["severity_counts"]:
        side_tables += "<h3>Severity, where a problem was found</h3>" + table(
            ["Severity", "Judgments"],
            [
                [esc(SEVERITY_LABELS.get(key, key)), str(value)]
                for key, value in sorted(
                    summary["severity_counts"].items(), key=lambda pair: -pair[1]
                )
            ],
            numeric=(1,),
        )
    if summary["confidence_counts"]:
        side_tables += "<h3>Evaluator confidence</h3>" + table(
            ["Confidence", "Judgments"],
            [
                [esc(key), str(value)]
                for key, value in sorted(
                    summary["confidence_counts"].items(), key=lambda pair: -pair[1]
                )
            ],
            numeric=(1,),
        )
    parts.append('<div class="card">' + side_tables + "</div>")

    parts.append(
        "<footer>"
        f"Extraction and evidence search ran on {esc(bundle.get('model'))} at "
        f"reasoning effort {esc(bundle.get('reasoning_effort'))}; each claim was "
        f"searched against up to {esc(bundle.get('max_excerpts'))} excerpts "
        f"({esc(bundle.get('excerpt_budget'))} characters) of the person's cached "
        f"materials. Bundle created {esc(bundle.get('created'))}. "
        f"Report generated {esc(datetime.now(timezone.utc).isoformat(timespec='seconds'))} "
        "by evaluation/factcheck/merge_results.py."
        "</footer>"
    )

    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />\n'
        f"<title>Fact check — {esc(bundle.get('name'))}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )


def write_report(summary: Dict[str, Any], path: Any) -> None:
    """Write the report, and the merged data beside it as JSON."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(render(summary))
    data_path = str(path).rsplit(".", 1)[0] + ".json"
    with open(data_path, "w", encoding="utf-8", newline="") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
