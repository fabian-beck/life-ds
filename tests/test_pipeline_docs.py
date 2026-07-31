"""Tests for the technical report build.

The point of these is narrow: the report is only trustworthy if the static
extraction really reads the source (rather than quietly returning nothing), if
the drift check really fails when the pipeline moves, and if a claim the authored
prose makes can never render as a silent gap. Everything else in the build is
presentation.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline_docs import facts as facts_module  # noqa: E402
from pipeline_docs import render, report, spec, teaser, validate  # noqa: E402
from pipeline_docs.introspect import scan_codebase, scan_script  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402

REPORT_SOURCE = REPO_ROOT / "docs" / "report" / "report.md"
ASSETS = SCRIPTS_DIR / "pipeline_docs" / "assets"


class IntrospectionTests(unittest.TestCase):
    """The static layer must read real facts out of the real scripts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.codebase = scan_codebase()

    def test_finds_every_generation_script(self) -> None:
        for name in (
            "generate_person_events.py",
            "generate_meta_story.py",
            "compose_meta_story.py",
            "translate_person.py",
        ):
            self.assertIn(name, self.codebase.scripts)

    def test_resolves_models_through_config_and_cli_defaults(self) -> None:
        calls = {
            (call.script, call.function): call for call in self.codebase.all_ai_calls()
        }
        phase1 = calls[("generate_person_events.py", "call_openai_phase1")]
        self.assertIn("gpt-", phase1.model_value or "")
        self.assertIn("OPENAI_MODEL", phase1.model_value or "")
        # Phase 1 reasons; the per-event research phase deliberately does not.
        self.assertIn("medium", phase1.reasoning_value or "")
        research = calls[("generate_person_events.py", "research_event_details")]
        self.assertIn("none", research.reasoning_value or "")

    def test_reads_reasoning_effort_through_the_typing_cast(self) -> None:
        """Typed-client call sites wrap the reasoning dict in ``cast(Any, ...)``.

        The effort constants are plain strings read from the environment, so the
        SDK's literal type needs a cast. The report must document the effort, not
        the cast wrapper.
        """
        for call in self.codebase.all_ai_calls():
            self.assertNotIn("cast(", call.reasoning_expr or "")

        source = (
            "def call_model(client, model):\n"
            "    return client.responses.parse(\n"
            "        model=model,\n"
            '        reasoning=cast(Any, {"effort": SOME_EFFORT}),\n'
            "        input=[],\n"
            "    )\n"
        )
        facts = scan_script(Path(self._write_temp(source)), {})
        self.assertEqual(facts.ai_calls[0].reasoning_expr, "SOME_EFFORT")

    def test_composer_uses_its_own_model_setting(self) -> None:
        calls = [
            call
            for call in self.codebase.all_ai_calls()
            if call.script == "compose_meta_story.py"
        ]
        self.assertTrue(calls)
        self.assertIn("COMPOSER", calls[0].model_value or "")

    def test_extracts_structured_output_schemas(self) -> None:
        schema = self.codebase.schema("EventDetails")
        self.assertIsNotNone(schema)
        assert schema is not None
        self.assertTrue(schema.fields)
        self.assertTrue(
            any(field.description for field in schema.fields),
            "expected at least one Field(description=...) to be captured",
        )

    def test_prompt_templates_keep_instructions_and_mark_injections(self) -> None:
        prompt = self.codebase.prompt(
            "generate_person_events.py", "build_phase2_prompt_base"
        )
        self.assertIsNotNone(prompt)
        assert prompt is not None
        self.assertIn("{", prompt.text, "injected data should stay marked")
        self.assertGreater(len(prompt.text), 500)

    def test_prompt_extraction_drops_console_output(self) -> None:
        """Progress prints are not prompt text and must not leak into the docs."""
        source = (
            "def build_x_prompt(name):\n"
            "    print('Generating something for', name)\n"
            "    parts = ', '.join(name)\n"
            "    prompt = 'REAL INSTRUCTION: describe the subject.'\n"
            "    if name:\n"
            "        prompt += f'Subject: {name}'\n"
            "    raise ValueError('this is an error message')\n"
        )
        path = Path(self._write_temp(source))
        facts = scan_script(path, {})
        prompt = facts.prompts["build_x_prompt"]
        self.assertIn("REAL INSTRUCTION", prompt.text)
        self.assertNotIn("Generating something", prompt.text)
        self.assertNotIn("this is an error message", prompt.text)
        self.assertNotIn(", ", prompt.segments[0].text)
        guarded = [segment for segment in prompt.segments if segment.conditions]
        self.assertTrue(guarded, "conditional prompt text should record its guard")
        self.assertIn("if name", guarded[0].conditions[0])

    def _write_temp(self, source: str) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        )
        handle.write(source)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def test_every_call_site_is_syntactically_reachable(self) -> None:
        """Guard against the scanner silently matching nothing."""
        self.assertGreaterEqual(len(self.codebase.all_ai_calls()), 20)


class DriftCheckTests(unittest.TestCase):
    """The check has to fail loudly, or documenting the pipeline is pointless."""

    def setUp(self) -> None:
        self.codebase = scan_codebase()
        self.original_steps = list(spec.STEPS)

    def tearDown(self) -> None:
        spec.STEPS[:] = self.original_steps

    def test_spec_matches_the_current_source(self) -> None:
        problems = [
            problem
            for problem in validate.check(self.codebase)
            if problem.severity == "error"
        ]
        self.assertEqual(
            problems, [], "spec.py no longer matches scripts/: " + str(problems)
        )

    def test_renamed_function_is_reported(self) -> None:
        step = next(item for item in spec.STEPS if item.id == "m_p8")
        original = step.function
        step.function = original + "_renamed"
        try:
            messages = [str(problem) for problem in validate.check(self.codebase)]
            self.assertTrue(any("no function" in message for message in messages))
        finally:
            step.function = original

    def test_undocumented_call_site_is_reported(self) -> None:
        spec.STEPS[:] = [item for item in self.original_steps if item.id != "m_p1"]
        messages = [str(problem) for problem in validate.check(self.codebase)]
        self.assertTrue(
            any("no step in spec.py claims it" in message for message in messages),
            "removing a step should surface its call site as uncovered",
        )


def _layers() -> dict:
    """Longest-path layer per step—the same rule the chart applies."""
    steps = {step.id: step for step in spec.STEPS}
    layers: dict = {}

    def layer(step_id: str) -> int:
        if step_id in layers:
            return layers[step_id]
        layers[step_id] = 0
        layers[step_id] = max(
            (layer(dep.on) + 1 for dep in steps[step_id].depends_on), default=0
        )
        return layers[step_id]

    for step_id in steps:
        layer(step_id)
    return layers


def _group_runs(group: spec.Group) -> list:
    """A group's steps cut into runs of consecutive layers, as the chart cuts them.

    Mirrors `buildBlocks` in `assets/app.js`: only a run is aligned and banded,
    which is what keeps a band from stretching over layers the group has no step
    in.
    """
    layers = _layers()
    ordered = sorted(group.steps, key=lambda step_id: layers[step_id])
    runs: list = []
    for step_id in ordered:
        layer = layers[step_id]
        if runs and layer - layers[runs[-1][-1]] <= 1:
            runs[-1].append(step_id)
        else:
            runs.append([step_id])
    return runs


class DependencyGraphTests(unittest.TestCase):
    """The chart claims to show real dependencies, so the graph has to be one."""

    def setUp(self) -> None:
        self.original_steps = list(spec.STEPS)

    def tearDown(self) -> None:
        spec.STEPS[:] = self.original_steps

    def test_every_edge_points_at_a_known_step_in_the_same_pipeline(self) -> None:
        known = {step.id: step for step in spec.STEPS}
        for step in spec.STEPS:
            for dep in step.depends_on:
                self.assertIn(dep.on, known, f"{step.id} depends on unknown {dep.on}")
                self.assertEqual(
                    step.id[:2],
                    dep.on[:2],
                    f"{step.id} depends across pipelines on {dep.on}",
                )
                self.assertTrue(dep.data, f"{step.id} -> {dep.on} has no data label")

    def test_graph_is_acyclic(self) -> None:
        problems = [str(problem) for problem in validate._check_graph()]
        self.assertEqual([], [text for text in problems if "cycle" in text])

    def test_a_cycle_fails_the_build(self) -> None:
        step = next(item for item in spec.STEPS if item.id == "m_p1")
        step.depends_on = [spec.Dep("m_save", "an impossible back-edge")]
        try:
            messages = [str(problem) for problem in validate._check_graph()]
            self.assertTrue(any("cycle" in message for message in messages))
        finally:
            step.depends_on = []

    def test_no_orchestrator_is_documented_as_a_step(self) -> None:
        """`main` only sequences the steps; drawing it flattens the fork."""
        for step in spec.STEPS:
            self.assertNotEqual(
                (step.script, step.function),
                ("generate_person.py", "main"),
            )
            self.assertNotEqual(
                (step.script, step.function),
                ("generate_meta_story.py", "main"),
            )

    def test_both_pipelines_really_branch(self) -> None:
        """A layer holding two steps is the whole reason for drawing a DAG."""
        layers = _layers()
        for prefix in ("p_", "m_"):
            widths: dict = {}
            for step in spec.STEPS:
                if step.id.startswith(prefix):
                    widths[layers[step.id]] = widths.get(layers[step.id], 0) + 1
            self.assertGreater(
                max(widths.values()),
                1,
                f"{prefix} pipeline drew as a chain, not a graph",
            )

    def test_map_branch_rates_before_it_clusters(self) -> None:
        """Ratings are the weights the clustering uses; the order is not free."""
        layers = _layers()
        self.assertLess(layers["m_p7b"], layers["m_p7a"])
        self.assertLess(layers["m_p7a"], layers["m_p7c"])

    def test_network_is_reviewed_before_circles_are_detected(self) -> None:
        layers = _layers()
        self.assertLess(layers["m_p5"], layers["m_p5b"])
        self.assertLess(layers["m_p5b"], layers["m_clusters"])


class GroupTests(unittest.TestCase):
    """Groups are what the chart aligns into one column, so they must be sane."""

    def setUp(self) -> None:
        self.original_groups = list(spec.GROUPS)

    def tearDown(self) -> None:
        spec.GROUPS[:] = self.original_groups

    def test_groups_name_known_steps_exactly_once(self) -> None:
        problems = [
            problem
            for problem in validate._check_groups()
            if problem.severity == "error"
        ]
        self.assertEqual(problems, [], str(problems))

    def test_a_step_in_two_groups_fails_the_build(self) -> None:
        spec.GROUPS.append(spec.Group("clash", "Clash", ["p_img_match", "p_write"]))
        messages = [str(problem) for problem in validate._check_groups()]
        self.assertTrue(any("already in group" in message for message in messages))

    def test_a_group_across_both_pipelines_fails_the_build(self) -> None:
        spec.GROUPS.append(spec.Group("mixed", "Mixed", ["p_write", "m_save"]))
        messages = [str(problem) for problem in validate._check_groups()]
        self.assertTrue(any("spans both pipelines" in message for message in messages))

    def test_every_group_aligns_at_least_one_run_of_two_steps(self) -> None:
        """A group that splits into nothing but single steps is never drawn.

        The chart aligns a group only where it occupies consecutive layers, so a
        group whose every run is one step long would produce no band at
        all—which means the grouping was wishful rather than structural.
        """
        for group in spec.GROUPS:
            runs = _group_runs(group)
            self.assertTrue(
                any(len(run) > 1 for run in runs),
                f"group '{group.id}' has no run of consecutive layers to align",
            )

    def test_the_imagery_group_splits_around_the_portrait(self) -> None:
        """The case the run-splitting exists for, pinned to the real graph."""
        group = spec.group_of("p_img_search")
        self.assertIsNotNone(group)
        assert group is not None
        runs = _group_runs(group)
        self.assertEqual(
            [len(run) for run in runs],
            [3, 1],
            "expected the three image steps to align and the portrait to detach",
        )
        self.assertEqual(runs[-1], ["p_portrait"])

    def test_every_group_stays_within_two_steps_per_layer(self) -> None:
        """Two members in one layer is legal but should not be the normal case."""
        layers = _layers()
        for group in spec.GROUPS:
            counts: dict = {}
            for step_id in group.steps:
                counts[layers[step_id]] = counts.get(layers[step_id], 0) + 1
            self.assertLessEqual(
                max(counts.values()),
                2,
                f"group '{group.id}' would be drawn more than two steps wide",
            )


class PayloadAndRenderTests(unittest.TestCase):
    """The page is a pure function of the payload, so test the payload."""

    @classmethod
    def setUpClass(cls) -> None:
        codebase = scan_codebase()
        cls.payload = build_payload(codebase, summaries={}, runs={"runs": []})

    def test_payload_covers_every_step(self) -> None:
        self.assertEqual(len(self.payload["steps"]), len(spec.STEPS))
        for step in self.payload["steps"]:
            self.assertIn(step["column"], {"person", "meta"})
            self.assertTrue(step["spec_summary"])

    def test_payload_carries_the_groups_the_chart_aligns(self) -> None:
        groups = {group["id"]: group for group in self.payload["groups"]}
        self.assertEqual(len(groups), len(spec.GROUPS))
        by_id = {step["id"]: step for step in self.payload["steps"]}
        for group in self.payload["groups"]:
            for step_id in group["steps"]:
                self.assertEqual(by_id[step_id]["group"], group["id"])
        self.assertIsNone(by_id["p_write"]["group"])

    def test_payload_carries_the_graph_the_chart_lays_out(self) -> None:
        by_id = {step["id"]: step for step in self.payload["steps"]}
        for step in self.payload["steps"]:
            for dep in step["depends_on"]:
                self.assertIn(dep["on"], by_id)
                self.assertTrue(dep["data"])
        self.assertTrue(by_id["p_translate"]["depends_on"])

    def test_ai_steps_carry_a_model_and_a_schema_or_prompt(self) -> None:
        for step in self.payload["steps"]:
            if step["kind"] != "ai":
                continue
            self.assertTrue(step["model"], f"{step['id']} has no resolved model")
            self.assertTrue(
                step["prompts"] or step["schemas"],
                f"{step['id']} has neither a prompt nor a schema",
            )

    def test_run_statistics_aggregate_recorded_calls(self) -> None:
        runs = {
            "runs": [
                {
                    "label": "test",
                    "calls": [
                        {
                            "step": "m_p1",
                            "duration_s": 4,
                            "usage": {"input_tokens": 100, "output_tokens": 10},
                        },
                        {
                            "step": "m_p1",
                            "duration_s": 6,
                            "usage": {"input_tokens": 200, "output_tokens": 20},
                        },
                    ],
                }
            ]
        }
        payload = build_payload(scan_codebase(), summaries={}, runs=runs)
        stats = next(step["stats"] for step in payload["steps"] if step["id"] == "m_p1")
        self.assertEqual(stats["calls"], 2)
        self.assertEqual(stats["total_s"], 10)
        self.assertEqual(stats["median_s"], 5)
        self.assertEqual(stats["input_tokens"], 300)

    def test_rendered_page_is_self_contained(self) -> None:
        html = render.render(self.payload)
        self.assertIn("window.PIPELINE", html)
        self.assertNotIn("</script>", json.dumps(self.payload))
        for marker in ("http://", "https://"):
            for tag in ("<script src=", '<link rel="stylesheet"'):
                self.assertNotIn(tag + '"' + marker, html)
        self.assertNotIn("__CSS__", html)
        self.assertNotIn("__DATA__", html)

    def test_embedded_payload_parses_as_json(self) -> None:
        html = render.render(self.payload)
        start = html.index('<script id="payload" type="application/json">') + len(
            '<script id="payload" type="application/json">'
        )
        end = html.index("</script>", start)
        data = json.loads(html[start:end].replace("<\\/", "</"))
        self.assertEqual(len(data["steps"]), len(spec.STEPS))

    def test_payload_carries_the_report_structure_the_sidebar_needs(self) -> None:
        codebase = scan_codebase()
        facts = facts_module.collect(codebase, {"runs": []})
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
        payload = build_payload(codebase, {}, {"runs": []}, document, facts)
        self.assertTrue(payload["report"]["sections"])
        self.assertEqual(payload["report"]["title"], document.title)
        self.assertEqual(len(payload["facts"]), len(facts))
        self.assertTrue(payload["script_index"]["generate_person.py"]["flags"])
        claimed = [site for site in payload["call_sites"] if site["step"]]
        self.assertEqual(len(claimed), len(payload["call_sites"]))

    def test_the_rendered_page_embeds_the_authored_body(self) -> None:
        codebase = scan_codebase()
        facts = facts_module.collect(codebase, {"runs": []})
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
        payload = build_payload(codebase, {}, {"runs": []}, document, facts)
        html = render.render(payload, document)
        self.assertIn(document.front["title"], html)
        self.assertIn('data-component="pipeline"', html)
        self.assertIn('id="introduction"', html)
        for marker in ("__BODY__", "__ABSTRACT__", "__TITLE__", "__SOURCE__"):
            self.assertNotIn(marker, html)


def _facts() -> dict:
    return facts_module.collect(scan_codebase(), {"runs": []})


def _compile(source: str, facts: dict | None = None) -> report.Document:
    return report.compile_report(source, facts if facts is not None else _facts())


class MarkdownCompilerTests(unittest.TestCase):
    """The authoring surface, exercised on small inputs rather than the report."""

    HEAD = "---\ntitle: T\n---\n"

    def test_front_matter_carries_a_folded_block(self) -> None:
        front, body, offset = report.split_front_matter(
            "---\ntitle: T\nabstract: first line\n  second line\n---\n\nbody\n"
        )
        self.assertEqual(front["title"], "T")
        self.assertEqual(front["abstract"], "first line\nsecond line")
        self.assertIn("body", body)
        self.assertGreater(offset, 0)

    def test_headings_are_numbered_anchored_and_nested(self) -> None:
        document = _compile(
            self.HEAD + "\n## One\n\n### One A\n\n### One B\n\n## Two\n\n### Two A\n"
        )
        numbers = [(section.number, section.title) for section in document.sections]
        self.assertEqual(numbers, [("1", "One"), ("2", "Two")])
        self.assertEqual(
            [child.number for child in document.sections[0].children], ["1.1", "1.2"]
        )
        self.assertEqual(
            [child.number for child in document.sections[1].children], ["2.1"]
        )
        self.assertIn('id="one-a"', document.html)

    def test_a_skipped_heading_level_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n#### Orphan\n")

    def test_a_citation_renders_with_its_provenance(self) -> None:
        facts = _facts()
        document = _compile(
            self.HEAD + "\n## S\n\nThere are {{ app.locales }}.\n", facts
        )
        self.assertIn("app.locales", document.citations)
        self.assertIn(facts["app.locales"].display, document.html)
        self.assertIn(facts["app.locales"].source.split(" ")[0], document.html)

    def test_an_unknown_citation_fails_the_build(self) -> None:
        """A hole in a sentence is worse than a broken build."""
        with self.assertRaises(report.ReportError) as caught:
            _compile(self.HEAD + "\n## S\n\nThere are {{ no.such.fact }}.\n")
        self.assertIn("no.such.fact", str(caught.exception))

    def test_citations_inside_a_fenced_block_are_left_alone(self) -> None:
        """The report documents its own syntax, so it has to be able to show it."""
        document = _compile(self.HEAD + "\n## S\n\n```text\n{{ data.people }}\n```\n")
        self.assertIn("{{ data.people }}", document.html)
        self.assertEqual(document.citations, [])

    def test_a_component_becomes_a_mount_point_with_its_arguments(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\n::: pipeline lane=person\nLead-in.\n:::\n"
        )
        self.assertEqual(len(document.mounts), 1)
        mount = document.mounts[0]
        self.assertEqual(mount.component, "pipeline")
        self.assertEqual(mount.params, {"lane": "person"})
        self.assertIn('data-component="pipeline"', document.html)
        self.assertIn('data-lane="person"', document.html)
        self.assertIn("Lead-in.", document.html)

    def test_an_unknown_component_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\n::: nonesuch\n:::\n")

    def test_a_component_missing_a_required_argument_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\n::: pipeline\n:::\n")

    def test_an_unclosed_component_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\n::: pipeline lane=person\n")

    def test_callouts_render_here_and_never_become_mount_points(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\n::: decision\nBecause.\n:::\n")
        self.assertEqual(document.mounts, [])
        self.assertIn("callout-decision", document.html)
        self.assertIn("Design decision", document.html)

    def test_captions_are_numbered_in_document_order(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\n::: steptable lane=person\n:::\n\n"
            "::: pipeline lane=meta\n:::\n\n::: steptable lane=meta\n:::\n"
        )
        self.assertEqual(
            [
                (mount.component, mount.figure_start, mount.table_start)
                for mount in document.mounts
            ],
            [("steptable", 1, 1), ("pipeline", 1, 2), ("steptable", 2, 2)],
        )

    def test_a_note_leaves_a_marker_and_prints_under_its_section(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\nA claim.^[Why it holds.]\n\n## T\n\nMore.\n"
        )
        self.assertEqual([note.number for note in document.notes], [1])
        self.assertIn('id="noteref-1"', document.html)
        self.assertIn('href="#note-1"', document.html)
        self.assertIn('id="note-1"', document.html)
        self.assertIn("Why it holds.", document.html)
        # The list closes the section that raised the note, not the report.
        self.assertLess(
            document.html.index('class="notes"'), document.html.index('id="t"')
        )

    def test_notes_are_numbered_across_the_document_and_grouped_by_section(
        self,
    ) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\nOne.^[First.]\n\nTwo.^[Second.]\n\n"
            "## T\n\nThree.^[Third.]\n"
        )
        self.assertEqual([note.number for note in document.notes], [1, 2, 3])
        self.assertIn('class="notes-list" start="1"', document.html)
        self.assertIn('class="notes-list" start="3"', document.html)

    def test_a_note_is_collected_even_when_its_block_spans_a_heading(self) -> None:
        """Extraction runs a block at a time; placement must not follow it."""
        document = _compile(
            self.HEAD + "\n## S\n\nBefore.^[Belongs to one.]\n\n## T\n\nAfter.\n"
        )
        first = document.html.index("Belongs to one.")
        self.assertLess(first, document.html.index('id="t"'))

    def test_a_note_carries_inline_markup_and_a_citation(self) -> None:
        facts = _facts()
        document = _compile(
            self.HEAD + "\n## S\n\nText.^[In `code`, and {{ app.locales }}.]\n", facts
        )
        self.assertIn("<code>code</code>", document.html)
        self.assertIn(facts["app.locales"].display, document.notes[0].body_html)

    def test_a_note_body_spanning_several_lines_becomes_one_line(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\nText.^[A body that\nwraps in the source.]\n"
        )
        self.assertEqual(
            document.notes[0].body_markdown, "A body that wraps in the source."
        )

    def test_note_syntax_inside_a_fenced_block_is_left_alone(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\n```text\nsee^[this]\n```\n")
        self.assertEqual(document.notes, [])
        self.assertIn("see^[this]", document.html)

    def test_an_escaped_note_marker_prints_as_text(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\nWrite \\^[like this].\n")
        self.assertEqual(document.notes, [])
        self.assertIn("^[like this]", document.html)

    def test_an_unclosed_note_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\nText.^[never closed\n")

    def test_an_empty_note_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\nText.^[]\n")

    def test_a_document_with_no_notes_renders_no_notes_block(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\nPlain.\n")
        self.assertNotIn("notes-list", document.html)
        self.assertNotIn("report:notes", document.html)

    def test_a_block_that_shows_nothing_consumes_no_caption_number(self) -> None:
        """Otherwise the sequence skips: Table 5 followed by Table 8."""

        def emits(component, params):
            if component == "runtable":
                return 0, 0
            return report.default_emits(component, params)

        source = (
            self.HEAD
            + "\n## S\n\n::: runtable lane=person\n:::\n\n::: steptable lane=person\n:::\n"
        )
        document = report.compile_report(source, _facts(), emits=emits)
        self.assertEqual(document.mounts[1].table_start, 1)


class ReportSourceTests(unittest.TestCase):
    """The real report has to resolve against the real code."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.codebase = scan_codebase()
        cls.facts = facts_module.collect(cls.codebase, {"runs": []})
        cls.document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), cls.facts
        )

    def test_the_report_source_exists_and_compiles(self) -> None:
        self.assertTrue(self.document.sections)
        self.assertTrue(self.document.mounts)
        self.assertTrue(self.document.front.get("abstract"))

    def test_the_report_has_no_unresolved_claims(self) -> None:
        problems = [
            str(problem)
            for problem in validate.check_report(
                self.document, self.facts, self.codebase
            )
            if problem.severity == "error"
        ]
        self.assertEqual(problems, [])

    def test_both_pipelines_are_drawn_as_subsections(self) -> None:
        """Two charts, not two tabs—the report has to read straight through."""
        lanes = [
            mount.params["lane"]
            for mount in self.document.mounts
            if mount.component == "pipeline"
        ]
        self.assertEqual(sorted(lanes), ["meta", "person"])
        subsections = [
            section.number
            for parent in self.document.sections
            for section in parent.children
        ]
        self.assertIn("4.1", subsections)
        self.assertIn("4.2", subsections)

    def test_the_prose_states_no_number_it_could_have_cited(self) -> None:
        """A transcribed count is the one thing this design exists to prevent."""
        source = REPORT_SOURCE.read_text(encoding="utf-8")
        body = report.split_front_matter(source)[1]
        for fact in self.facts.values():
            if fact.value is None or fact.value < 10:
                continue  # small integers appear in ordinary prose
            self.assertNotIn(
                fact.display,
                body,
                f"report.md writes {fact.display!r} literally; cite "
                f"{{{{ {fact.key} }}}} instead",
            )

    def test_every_note_in_the_report_is_readable_both_ways(self) -> None:
        """The popover copies the printed list, so every marker needs an item."""
        self.assertTrue(self.document.notes, "the report demonstrates no note")
        for note in self.document.notes:
            self.assertIn(f'id="noteref-{note.number}"', self.document.html)
            self.assertIn(f'id="note-{note.number}"', self.document.html)
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        css = (ASSETS / "style.css").read_text(encoding="utf-8")
        self.assertIn("renderNotePopovers", js)
        self.assertIn("body.has-note-pop .notes", css)

    def test_every_mounted_component_has_a_renderer_in_the_page(self) -> None:
        """The two rosters are what keep a block from rendering as a blank."""
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        for name in sorted(report.COMPONENTS):
            self.assertRegex(
                js,
                rf"\n    {name}: function",
                f"app.js has no renderer for '::: {name}'",
            )


class TeaserTests(unittest.TestCase):
    """The teaser figure, and the prose's references into it.

    A figure the prose points at is only as trustworthy as the resolution of
    those pointers, so the checks here are the geometric and referential ones a
    reader cannot make: that the drawing's boxes really are where the focus
    machinery will look for them, and that every phrase naming a part names one
    that exists.
    """

    HEAD = "---\ntitle: T\n---\n"

    def test_the_scene_is_geometrically_sound(self) -> None:
        problems = [
            f"{problem.where}: {problem.message}"
            for problem in teaser.check_scene(list(_facts()))
            if problem.severity == "error"
        ]
        self.assertEqual(problems, [])

    def test_every_part_carries_a_label_and_a_sentence(self) -> None:
        self.assertGreater(len(teaser.PARTS), 8)
        for part in teaser.PARTS:
            self.assertTrue(part.label.strip(), f"{part.id} has no label")
            self.assertTrue(part.blurb.strip(), f"{part.id} has no blurb")

    def test_figure_metrics_cite_measured_facts(self) -> None:
        """The figure prints numbers; they come from facts.py or nowhere."""
        facts = _facts()
        for key in teaser.fact_keys():
            self.assertIn(key, facts)

    def test_every_decor_has_a_drawing_routine_in_the_page(self) -> None:
        """The same closed-roster contract the components have with report.py."""
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        for name in sorted({part.decor for part in teaser.PARTS}):
            self.assertRegex(
                js,
                rf"\n    {name}: function",
                f"app.js has no teaser decor routine for '{name}'",
            )

    def test_a_reference_becomes_a_control_that_names_its_part(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\nDerived as [[timeline|a chronology]].\n"
        )
        self.assertIn("timeline", document.figrefs)
        self.assertIn('class="figref" data-part="timeline"', document.html)
        self.assertIn("a chronology", document.html)

    def test_a_reference_without_a_phrase_uses_the_part_label(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\nSee [[map]].\n")
        self.assertIn(teaser.part_by_id("map").label, document.html)

    def test_an_unknown_part_fails_the_build(self) -> None:
        """A phrase that lights nothing is the figure's version of a silent gap."""
        with self.assertRaises(report.ReportError) as caught:
            _compile(self.HEAD + "\n## S\n\nSee [[no-such-part|this]].\n")
        self.assertIn("no-such-part", str(caught.exception))

    def test_references_inside_a_fenced_block_are_left_alone(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\n```text\n[[timeline|a chronology]]\n```\n"
        )
        self.assertIn("[[timeline|a chronology]]", document.html)
        self.assertEqual(document.figrefs, [])

    def test_a_reference_with_no_figure_on_the_page_is_an_error(self) -> None:
        facts = _facts()
        document = report.compile_report(
            self.HEAD + "\n## S\n\nSee [[map|the map]].\n", facts
        )
        problems = [
            problem
            for problem in validate.check_report(document, facts, scan_codebase())
            if problem.severity == "error" and "teaser" in problem.message
        ]
        self.assertTrue(problems)

    def test_the_report_draws_the_figure_and_points_at_every_part(self) -> None:
        source = REPORT_SOURCE.read_text(encoding="utf-8")
        document = report.compile_report(source, _facts())
        self.assertIn("teaser", [mount.component for mount in document.mounts])
        unreferenced = sorted(set(teaser.part_ids()) - set(document.figrefs))
        self.assertEqual(unreferenced, [])

    def test_the_figure_is_the_first_numbered_figure(self) -> None:
        """A teaser that is not Figure 1 is not a teaser."""
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), _facts()
        )
        teaser_mount = next(
            mount for mount in document.mounts if mount.component == "teaser"
        )
        self.assertEqual(teaser_mount.figure_start, 1)

    def test_the_scene_travels_in_the_payload(self) -> None:
        codebase = scan_codebase()
        payload = build_payload(codebase, {}, {"runs": []})
        self.assertEqual(
            [part["id"] for part in payload["teaser"]["parts"]],
            teaser.part_ids(),
        )


class FactTests(unittest.TestCase):
    """A cited number is only worth citing if it was really measured."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = facts_module.collect(scan_codebase(), {"runs": []})

    def test_every_fact_has_a_display_value_and_a_source(self) -> None:
        self.assertGreater(len(self.facts), 10)
        for key, fact in self.facts.items():
            self.assertEqual(key, fact.key)
            self.assertTrue(fact.display, f"{key} has no display value")
            self.assertTrue(fact.source, f"{key} does not say where it came from")

    def test_repository_measurements_are_not_silently_zero(self) -> None:
        """A directory listing that fails quietly would read as a real zero."""
        for key in ("app.locales", "pipeline.prompt_builders", "pipeline.schemas"):
            self.assertGreater(self.facts[key].value or 0, 0, f"{key} measured nothing")

    def test_pipeline_measurements_agree_with_the_spec(self) -> None:
        self.assertEqual(self.facts["pipeline.steps"].value, len(spec.STEPS))
        self.assertEqual(
            (self.facts["pipeline.person_steps"].value or 0)
            + (self.facts["pipeline.meta_steps"].value or 0),
            len(spec.STEPS),
        )

    def test_model_names_are_identifiers_not_expressions(self) -> None:
        """The prose cites this inline, so it must not carry env-var noise."""
        display = self.facts["pipeline.models"].display
        self.assertNotIn("(", display)
        self.assertIn("gpt-", display)


class AssetTests(unittest.TestCase):
    def test_page_has_no_dark_mode(self) -> None:
        """Light-only was an explicit request; keep it from creeping back."""
        css = (ASSETS / "style.css").read_text(encoding="utf-8")
        self.assertNotIn("prefers-color-scheme", css)
        self.assertNotIn('data-theme="dark"', css)

    def test_javascript_parses_and_uses_no_network(self) -> None:
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "XMLHttpRequest", "import("):
            self.assertNotIn(forbidden, js)

    def test_the_page_no_longer_switches_pipelines_with_a_tab(self) -> None:
        """Both charts are on the page at once; keep the tabs from returning."""
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        css = (ASSETS / "style.css").read_text(encoding="utf-8")
        for forbidden in ("pipeline-tab", 'role: "tab"'):
            self.assertNotIn(forbidden, js)
        self.assertNotIn(".pipeline-tab", css)

    def test_spec_module_has_no_syntax_drift(self) -> None:
        source = (SCRIPTS_DIR / "pipeline_docs" / "spec.py").read_text(encoding="utf-8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
