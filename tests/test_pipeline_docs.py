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
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline_docs import bibliography, concepts  # noqa: E402
from pipeline_docs import facts as facts_module  # noqa: E402
from pipeline_docs import render, report, screenshots  # noqa: E402
from pipeline_docs import spec, teaser, validate  # noqa: E402
from pipeline_docs.introspect import scan_codebase, scan_script  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402

REPORT_SOURCE = REPO_ROOT / "docs" / "report" / "report.md"
REFERENCES = REPO_ROOT / "docs" / "report" / "references.bib"
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

    def test_no_edge_is_implied_by_a_longer_chain(self) -> None:
        """A shortcut beside a strand is a second line saying the first thing."""
        redundant = [
            str(problem)
            for problem in validate._check_graph()
            if "already implied by" in problem.message
        ]
        self.assertEqual([], redundant)

    def test_a_redundant_edge_is_reported_with_the_chain_that_implies_it(self) -> None:
        step = next(item for item in spec.STEPS if item.id == "p_img_match")
        original = list(step.depends_on)
        step.depends_on = original + [spec.Dep("p_events_p1", "event skeletons")]
        try:
            messages = [
                problem.message
                for problem in validate._check_graph()
                if "already implied by" in problem.message
            ]
            self.assertEqual(1, len(messages))
            self.assertIn(
                "p_events_p1 -> p_img_search -> p_img_fetch -> p_img_match",
                messages[0],
            )
        finally:
            step.depends_on = original

    def test_removing_a_redundant_edge_leaves_every_layer_where_it_was(self) -> None:
        """Why the reduction is safe: the longest path does not move."""
        before = _layers()
        step = next(item for item in spec.STEPS if item.id == "p_img_match")
        original = list(step.depends_on)
        step.depends_on = original + [spec.Dep("p_events_p1", "event skeletons")]
        try:
            self.assertEqual(before, _layers())
        finally:
            step.depends_on = original

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
        cls.payload = build_payload(codebase, summaries={})

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
        facts = facts_module.collect(codebase)
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
        payload = build_payload(codebase, {}, document, facts)
        self.assertTrue(payload["report"]["sections"])
        self.assertEqual(payload["report"]["title"], document.title)
        self.assertEqual(len(payload["facts"]), len(facts))
        self.assertTrue(payload["script_index"]["generate_person.py"]["flags"])
        claimed = [site for site in payload["call_sites"] if site["step"]]
        self.assertEqual(len(claimed), len(payload["call_sites"]))

    def test_the_shell_carries_every_element_the_script_reaches_for(self) -> None:
        """`app.js` wires the drawer and the chart modal up on load.

        Every one of those lookups is unconditional, so an element dropped from
        the template in `render.py` would not degrade the page—it would throw
        before a single computed block was hydrated, and the report would render
        as a column of "this block is computed when the report is built".
        """
        script = (ASSETS / "app.js").read_text(encoding="utf-8")
        wanted = set(re.findall(r'getElementById\("([a-z0-9-]+)"\)', script))
        self.assertIn("chart-modal", wanted)
        html = render.render(self.payload)
        for element_id in sorted(wanted):
            self.assertIn(f'id="{element_id}"', html, f"the shell has no #{element_id}")

    def test_each_figure_size_states_the_type_its_stylesheet_sets(self) -> None:
        """The chart picks a level of detail by how large its names would come out.

        The step name is sized in `style.css` but weighed in `app.js`, which
        keeps a `TITLE_PX` beside each size to weigh it with. Nothing at runtime
        would notice the two disagreeing—the figure would simply start choosing
        the wrong drawing for the column, which is not a thing a reader can see
        is wrong.
        """
        script = (ASSETS / "app.js").read_text(encoding="utf-8")
        css = (ASSETS / "style.css").read_text(encoding="utf-8")

        claimed = {
            name: int(px)
            for name, px in re.findall(
                r"^\s{4}(full|mid|compact): \{\n\s+TITLE_PX: (\d+)",
                script,
                flags=re.MULTILINE,
            )
        }
        self.assertEqual(set(claimed), {"full", "mid", "compact"})

        for size, expected in claimed.items():
            # `full` is the plain node rule; the reduced sizes override it.
            selector = ".node text.title" if size == "full" else f".flow-{size} &"
            pattern = (
                r"(?<!flow-mid )(?<!flow-compact )\.node text\.title \{[^}]*?"
                r"font-size: (\d+(?:\.\d+)?)px"
                if size == "full"
                else rf"\.flow-{size} \.node text\.title \{{[^}}]*?"
                rf"font-size: (\d+(?:\.\d+)?)px"
            )
            found = re.search(pattern, css, flags=re.DOTALL)
            self.assertIsNotNone(found, f"style.css sets no title size for {selector}")
            assert found is not None
            self.assertEqual(
                float(found.group(1)),
                float(expected),
                f"app.js weighs the {size} figure's names at {expected}px but "
                f"style.css sets them at {found.group(1)}px",
            )

    def test_the_rendered_page_embeds_the_authored_body(self) -> None:
        codebase = scan_codebase()
        facts = facts_module.collect(codebase)
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
        payload = build_payload(codebase, {}, document, facts)
        html = render.render(payload, document)
        self.assertIn(document.front["title"], html)
        self.assertIn('data-component="pipeline"', html)
        self.assertIn('id="introduction"', html)
        for marker in (
            "__BODY__",
            "__ABSTRACT__",
            "__TITLE__",
            "__SOURCE__",
            "__AUTHORS__",
        ):
            self.assertNotIn(marker, html)

    def test_the_title_block_names_the_authors_without_scripting(self) -> None:
        """The byline is served HTML: no reader should have to run JS for it."""
        codebase = scan_codebase()
        facts = facts_module.collect(codebase)
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"), facts
        )
        payload = build_payload(codebase, {}, document, facts)
        head = render.render(payload, document).split('<div class="report"')[0]
        self.assertTrue(document.authors, "the report source declares no authors")
        for author in document.authors:
            self.assertIn(author.name, head)
            if author.affiliation:
                self.assertIn(author.affiliation, head)
            if author.url:
                self.assertIn(author.url, head)
            if author.orcid:
                self.assertIn(f"https://orcid.org/{author.orcid}", head)


def _facts() -> dict:
    return facts_module.collect(scan_codebase())


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

    def test_authors_are_read_from_the_front_matter(self) -> None:
        document = _compile(
            "---\ntitle: T\nauthors:\n"
            "  Ada Lovelace | Analytical Society | https://example.org/ada"
            " | 0000-0001-2345-6789\n"
            "  Alan Turing\n"
            "---\n\n## S\n\nbody\n"
        )
        first, second = document.authors
        self.assertEqual(first.name, "Ada Lovelace")
        self.assertEqual(first.affiliation, "Analytical Society")
        self.assertEqual(first.url, "https://example.org/ada")
        self.assertEqual(first.orcid_url, "https://orcid.org/0000-0001-2345-6789")
        self.assertEqual(second.name, "Alan Turing")
        self.assertEqual((second.affiliation, second.url, second.orcid), ("", "", ""))

    def test_an_orcid_is_stored_bare_however_it_was_written(self) -> None:
        authors = report.parse_authors(
            "A | X | | https://orcid.org/0000-0002-1825-0097\n"
            "B | X | | 0000-0002-1825-009X\n"
        )
        self.assertEqual(authors[0].orcid, "0000-0002-1825-0097")
        self.assertEqual(authors[1].orcid, "0000-0002-1825-009X")

    def test_a_mistyped_orcid_fails_the_build(self) -> None:
        """Pointing a reader at a stranger's record is worse than no link."""
        with self.assertRaises(report.ReportError):
            report.parse_authors("A | X | | 0000-0002-1825\n")

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
            self.HEAD + "\n## S\n\nThere are {{ app.languages }}.\n", facts
        )
        self.assertIn("app.languages", document.citations)
        self.assertIn(facts["app.languages"].display, document.html)
        self.assertIn(facts["app.languages"].source.split(" ")[0], document.html)

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
            self.HEAD + "\n## S\n\nText.^[In `code`, and {{ app.languages }}.]\n", facts
        )
        self.assertIn("<code>code</code>", document.html)
        self.assertIn(facts["app.languages"].display, document.notes[0].body_html)

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


class PrincipleTests(unittest.TestCase):
    """A principle is declared once, numbered here, and referenced by number."""

    HEAD = "---\ntitle: T\n---\n"
    BLOCK = (
        "::: principles\n"
        "@first One record\n"
        "The event is the unit.\n"
        "\n"
        "@second Revise top-down\n"
        "A closing pass reads the whole.\n"
        ":::\n"
    )

    def test_principles_are_numbered_in_declaration_order(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\n" + self.BLOCK)
        self.assertEqual(
            [(item.number, item.id, item.label) for item in document.principles],
            [(1, "first", "P1"), (2, "second", "P2")],
        )
        self.assertIn('id="principle-1"', document.html)
        self.assertIn("The event is the unit.", document.html)

    def test_a_reference_renders_as_the_number_and_links_to_the_list(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\nBecause it holds ((second)).\n\n" + self.BLOCK
        )
        self.assertEqual(document.prefs, ["second"])
        self.assertIn('class="pref" href="#principle-2"', document.html)
        self.assertIn('data-pop-label="Principle 2"', document.html)
        self.assertIn(">P2</a>", document.html)

    def test_a_reference_may_stand_above_the_block_that_declares_it(self) -> None:
        """The declaration is read before compiling, not while walking it."""
        document = _compile(self.HEAD + "\n## S\n\nUp here ((first)).\n\n" + self.BLOCK)
        self.assertEqual(document.prefs, ["first"])

    def test_an_unknown_principle_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\nText ((missing)).\n\n" + self.BLOCK)

    def test_a_reference_with_no_block_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\nText ((first)).\n")

    def test_two_principles_may_not_share_an_id(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(
                self.HEAD + "\n## S\n\n::: principles\n@same One\nA.\n\n"
                "@same Two\nB.\n:::\n"
            )

    def test_a_principle_without_text_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\n::: principles\n@lonely Title only\n:::\n")

    def test_a_second_principles_block_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            _compile(self.HEAD + "\n## S\n\n" + self.BLOCK + "\n" + self.BLOCK)

    def test_reference_syntax_inside_a_fenced_block_is_left_alone(self) -> None:
        document = _compile(
            self.HEAD + "\n## S\n\n```\n((first))\n```\n\n" + self.BLOCK
        )
        self.assertEqual(document.prefs, [])
        self.assertIn("((first))", document.html)

    def test_an_escaped_reference_prints_as_text(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\nWrite \\((first)).\n\n" + self.BLOCK)
        self.assertEqual(document.prefs, [])
        self.assertIn("((first))", document.html)

    def test_a_principle_body_may_cite_a_measurement(self) -> None:
        facts = _facts()
        document = _compile(
            self.HEAD + "\n## S\n\n::: principles\n@one Localized throughout\n"
            "Every document exists in {{ app.languages }}.\n:::\n",
            facts,
        )
        self.assertIn(facts["app.languages"].display, document.principles[0].body_html)

    def test_a_principle_nothing_references_is_reported(self) -> None:
        document = _compile(self.HEAD + "\n## S\n\nText ((first)).\n\n" + self.BLOCK)
        messages = [
            problem.message
            for problem in validate._check_principles(document)
            if problem.severity == "warning"
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("second", messages[0])


class BibliographyTests(unittest.TestCase):
    """A reference is only a reference if it resolves."""

    SAMPLE = """
@article{one,
  author  = {Segel, Edward and Heer, Jeffrey},
  title   = {Narrative Visualization},
  journal = {IEEE TVCG},
  volume  = {16},
  number  = {6},
  pages   = {1139--1148},
  year    = {2010},
  doi     = {10.1109/TVCG.2010.179}
}

@misc{two,
  author = {Kr{\\"o}tzsch, Markus},
  title  = {Something},
  note   = {arXiv:1234.5678},
  year   = {2023},
  doi    = {10.48550/arXiv.1234.5678}
}
"""

    def _parse(self) -> bibliography.Bibliography:
        return bibliography.parse(self.SAMPLE, "sample.bib")

    def test_entries_are_read_with_their_fields(self) -> None:
        bib = self._parse()
        self.assertEqual(sorted(bib.keys()), ["one", "two"])
        entry = bib.get("one")
        assert entry is not None
        self.assertEqual(entry.kind, "article")
        self.assertEqual(entry.doi, "10.1109/TVCG.2010.179")
        self.assertEqual(entry.url, "https://doi.org/10.1109/TVCG.2010.179")
        self.assertEqual(
            entry.describe(),
            "E. Segel and J. Heer, “Narrative Visualization,” IEEE TVCG, "
            "vol. 16, no. 6, pp. 1139–1148, 2010, "
            "doi: 10.1109/TVCG.2010.179.",
        )

    def test_the_author_block_is_ieee_and_names_everyone(self) -> None:
        """Initials lead, a serial comma closes, and nobody becomes 'et al.'"""
        self.assertEqual(
            bibliography.format_names("Segel, Edward and Heer, Jeffrey"),
            "E. Segel and J. Heer",
        )
        self.assertEqual(
            bibliography.format_names("Henry Riche, Nathalie"), "N. Henry Riche"
        )
        self.assertEqual(
            bibliography.format_names(
                "Clauset, Aaron and Newman, M. E. J. and Moore, Cristopher"
            ),
            "A. Clauset, M. E. J. Newman, and C. Moore",
        )
        many = " and ".join(f"Family{n}, Given{n}" for n in range(1, 11))
        self.assertNotIn("et al", bibliography.format_names(many))
        self.assertEqual(bibliography.format_names(many).count("."), 10)

    def test_a_proceedings_entry_reads_as_ieee_prints_one(self) -> None:
        """No imprint, and no year repeated out of a title that carries it."""
        bib = bibliography.parse(
            "@inproceedings{k, author = {Doe, Jane and Roe, Richard},"
            " title = {A Paper}, booktitle = {2021 Some Conference},"
            " pages = {156--160}, publisher = {IEEE}, year = {2021},"
            " doi = {10/k}}"
        )
        entry = bib.get("k")
        assert entry is not None
        self.assertEqual(
            entry.describe(),
            "J. Doe and R. Roe, “A Paper,” in 2021 Some Conference, "
            "pp. 156–160, doi: 10/k.",
        )

    def test_a_year_the_container_does_not_carry_is_printed(self) -> None:
        bib = bibliography.parse(
            "@inproceedings{k, author = {Doe, Jane}, title = {A Paper},"
            " booktitle = {Some Conference}, pages = {1--2}, year = {2021},"
            " doi = {10/k}}"
        )
        entry = bib.get("k")
        assert entry is not None
        self.assertIn("pp. 1–2, 2021, doi: 10/k.", entry.describe())

    def test_an_article_number_replaces_a_page_range(self) -> None:
        bib = bibliography.parse(
            "@article{k, author = {Doe, Jane}, title = {A Paper},"
            " journal = {A Journal}, volume = {70}, number = {6},"
            " articleno = {066111}, year = {2004}, doi = {10/k}}"
        )
        entry = bib.get("k")
        assert entry is not None
        self.assertIn("vol. 70, no. 6, Art. no. 066111, 2004,", entry.describe())

    def test_bibtex_accents_are_decoded_for_the_page(self) -> None:
        entry = self._parse().get("two")
        assert entry is not None
        self.assertEqual(entry.people(), "M. Krötzsch")

    def test_a_folded_value_becomes_one_line(self) -> None:
        bib = bibliography.parse(
            "@misc{k,\n  title = {A very\n           long title},\n"
            "  author = {Doe, Jane},\n  year = {2020},\n  doi = {10/x}\n}\n"
        )
        entry = bib.get("k")
        assert entry is not None
        self.assertEqual(entry.title(), "A very long title")

    def test_an_entry_without_a_doi_is_an_error(self) -> None:
        bib = bibliography.parse(
            "@misc{k,\n title = {T},\n author = {Doe, Jane},\n year = {2020}\n}\n"
        )
        problems = bibliography.check(bib, ["k"])
        self.assertIn(("error", "reference 'k' has no doi—every entry has to be "
                       "resolvable, so add one or drop the entry"), problems)

    def test_an_uncited_entry_is_reported_as_drift(self) -> None:
        problems = bibliography.check(self._parse(), ["one"])
        self.assertEqual(
            problems, [("warning", "reference 'two' is declared but never cited")]
        )

    def test_a_duplicate_key_fails_the_parse(self) -> None:
        with self.assertRaises(bibliography.BibliographyError):
            bibliography.parse(self.SAMPLE + self.SAMPLE)

    def test_the_shipped_bibliography_is_complete(self) -> None:
        """The file the report ships with has to pass its own rules."""
        bib = bibliography.load(REFERENCES)
        self.assertTrue(bib.keys())
        errors = [
            message
            for severity, message in bibliography.check(bib, bib.keys())
            if severity == "error"
        ]
        self.assertEqual(errors, [])


class ReferenceCitationTests(unittest.TestCase):
    """`[@key]` is checked and numbered the way `{{ fact }}` is."""

    HEAD = "---\ntitle: T\n---\n"
    BIB = bibliography.parse(
        "@misc{a, title = {A}, author = {Ada, Ann}, year = {2001}, doi = {10/a}}\n"
        "@misc{b, title = {B}, author = {Bo, Ben}, year = {2002}, doi = {10/b}}\n"
    )

    def _compile(self, body: str) -> report.Document:
        return report.compile_report(self.HEAD + body, _facts(), bib=self.BIB)

    def test_citations_are_numbered_by_first_use(self) -> None:
        document = self._compile(
            "\n## S\n\nSecond [@b], first [@a], again [@b].\n\n::: references\n:::\n"
        )
        self.assertEqual(document.refcites, ["b", "a"])
        self.assertEqual([entry.key for entry in document.references], ["b", "a"])
        self.assertIn('href="#ref-1"', document.html)
        self.assertIn('id="ref-2"', document.html)
        self.assertEqual(document.html.count('href="#ref-1"'), 2)

    def test_several_keys_share_one_bracket(self) -> None:
        document = self._compile("\n## S\n\nBoth [@a; @b].\n\n::: references\n:::\n")
        self.assertEqual(document.refcites, ["a", "b"])
        self.assertIn(
            '<span class="refcite">[<a class="refref" href="#ref-1"',
            document.html.replace("\n", ""),
        )

    def test_an_unknown_reference_fails_the_build(self) -> None:
        with self.assertRaises(report.ReportError) as caught:
            self._compile("\n## S\n\nText [@nope].\n")
        self.assertIn("nope", str(caught.exception))

    def test_a_citation_split_across_lines_fails_the_build(self) -> None:
        """Otherwise it renders as literal brackets in the middle of a sentence."""
        with self.assertRaises(report.ReportError) as caught:
            self._compile("\n## S\n\nText [@a;\n@b].\n")
        self.assertIn("one line", str(caught.exception))

    def test_citation_syntax_inside_a_fenced_block_is_left_alone(self) -> None:
        document = self._compile("\n## S\n\n```text\n[@a]\n```\n")
        self.assertIn("[@a]", document.html)
        self.assertEqual(document.refcites, [])

    def test_an_escaped_citation_prints_as_text(self) -> None:
        document = self._compile("\n## S\n\nWrite \\[@a] to cite.\n")
        self.assertIn("[@a]", document.html)
        self.assertEqual(document.refcites, [])

    def test_the_list_prints_the_entry_with_its_doi_as_a_link(self) -> None:
        document = self._compile("\n## S\n\nText [@a].\n\n## R\n\n::: references\n:::\n")
        self.assertTrue(document.prints_references)
        self.assertIn('href="https://doi.org/10/a"', document.html)
        self.assertIn("doi: ", document.html)
        self.assertIn(">10/a</a>", document.html)

    def test_a_citation_opens_its_entry_the_way_a_note_does(self) -> None:
        """Same marker contract as a note: a real link, and a pop-body to copy."""
        document = self._compile("\n## S\n\nText [@a].\n\n::: references\n:::\n")
        self.assertIn('class="refref" href="#ref-1"', document.html)
        self.assertIn('data-pop-label="[1]"', document.html)
        self.assertIn('id="ref-1"', document.html)
        self.assertRegex(document.html, r'id="ref-1"[^>]*>\s*<span class="pop-body">')
        self.assertIn('target="_blank"', document.html)

    def test_a_note_may_cite_a_work(self) -> None:
        document = self._compile(
            "\n## S\n\nText.^[As shown [@a].]\n\n::: references\n:::\n"
        )
        self.assertEqual(document.refcites, ["a"])
        self.assertIn('href="#ref-1"', document.notes[0].body_html)

    def test_a_document_with_no_citations_prints_no_list(self) -> None:
        document = self._compile("\n## S\n\nPlain.\n\n::: references\n:::\n")
        self.assertEqual(document.references, [])
        self.assertNotIn("reference-list", document.html)
        self.assertNotIn("report:references", document.html)

    def test_two_reference_blocks_fail_the_build(self) -> None:
        with self.assertRaises(report.ReportError):
            self._compile("\n## S\n\n::: references\n:::\n\n::: references\n:::\n")


class ReportSourceTests(unittest.TestCase):
    """The real report has to resolve against the real code."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.codebase = scan_codebase()
        cls.facts = facts_module.collect(cls.codebase)
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

    def test_the_report_cites_work_and_prints_the_list(self) -> None:
        self.assertTrue(self.document.refcites)
        self.assertTrue(self.document.prints_references)
        self.assertEqual(
            [entry.key for entry in self.document.references], self.document.refcites
        )
        for entry in self.document.references:
            self.assertTrue(entry.doi, f"{entry.key} has no doi")
            self.assertIn(f'href="https://doi.org/{entry.doi}"', self.document.html)

    def test_the_prose_states_no_number_it_could_have_cited(self) -> None:
        """A transcribed count is the one thing this design exists to prevent.

        Directive lines are excluded: a screenshot's viewport and a route that
        names an event index are addresses the browser is given, not claims the
        report makes, and they are read by nobody as prose. Citation keys are
        excluded for the same reason—`[@fruchterman1991graph]` names a work, and
        the year inside the key is part of its address rather than a number the
        report states.
        """
        source = REPORT_SOURCE.read_text(encoding="utf-8")
        body = "\n".join(
            report.REFCITE.sub("", line)
            for line in report.split_front_matter(source)[1].splitlines()
            if not line.startswith(":::")
        )
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
        self.assertIn("renderPopovers", js)
        self.assertIn("body.has-note-pop .notes", css)

    def test_every_principle_is_stated_once_and_acted_on_somewhere(self) -> None:
        """The numbering is only worth having if the report uses it."""
        self.assertTrue(self.document.principles, "the report states no principle")
        for item in self.document.principles:
            self.assertIn(f'id="principle-{item.number}"', self.document.html)
            self.assertIn(
                item.id,
                self.document.prefs,
                f"principle {item.label} is declared but never referenced",
            )
        self.assertIn('class="pref"', self.document.html)

    def test_a_principle_marker_reads_the_same_way_a_note_marker_does(self) -> None:
        """Both markers are links into printed text the popover copies."""
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        self.assertIn('querySelector(".pop-body")', js)
        self.assertIn('data-pop-label', js)
        self.assertIn('class="principle-body pop-body"', self.document.html)
        self.assertIn('class="note-body pop-body"', self.document.html)

    def test_every_mounted_component_has_a_renderer_in_the_page(self) -> None:
        """The two rosters are what keep a block from rendering as a blank."""
        js = (ASSETS / "app.js").read_text(encoding="utf-8")
        for name in sorted(report.COMPONENTS):
            self.assertRegex(
                js,
                rf"\n    {name}: function",
                f"app.js has no renderer for '::: {name}'",
            )


class ScreenshotTests(unittest.TestCase):
    """Figures of the interface are described, so the description must hold.

    A screenshot is the one figure in the report that no reader and no build can
    re-derive by reading the source. What keeps it honest is that the position it
    was taken from is written down and checked: the picture must exist, and the
    build must notice when the declaration it was taken from has moved.
    """

    HEAD = "---\ntitle: T\n---\n"

    @staticmethod
    def _block(**params) -> str:
        settings = dict(
            id="shot-one",
            route="#/en/story/ada_lovelace",
            caption="A story slide",
        )
        settings.update(params)
        arguments = " ".join(f'{key}="{value}"' for key, value in settings.items())
        return f"\n## S\n\n::: screenshot {arguments}\n:::\n"

    def test_a_declaration_becomes_a_typed_shot(self) -> None:
        document = _compile(
            self.HEAD
            + self._block(width=390, height=844, clip="0,0,390,200", format="png")
        )
        shot = screenshots.parse(document.mounts[0].params)
        self.assertEqual(shot.route, "#/en/story/ada_lovelace")
        self.assertEqual(shot.css_size, (390, 200))
        self.assertEqual(shot.clip, (0, 0, 390, 200))
        self.assertEqual(shot.file_name, "shot-one.png")

    def test_the_fingerprint_covers_the_position_and_not_the_prose(self) -> None:
        """Otherwise an editing pass would report every figure as stale."""
        base = screenshots.parse({"id": "a", "route": "#/en", "caption": "One"})
        reworded = screenshots.parse({"id": "a", "route": "#/en", "caption": "Other"})
        moved = screenshots.parse({"id": "a", "route": "#/de", "caption": "One"})
        resized = screenshots.parse(
            {"id": "a", "route": "#/en", "caption": "One", "width": "390"}
        )
        self.assertEqual(base.fingerprint, reworded.fingerprint)
        self.assertNotEqual(base.fingerprint, moved.fingerprint)
        self.assertNotEqual(base.fingerprint, resized.fingerprint)

    def test_a_declaration_that_describes_no_capture_is_rejected(self) -> None:
        for params in (
            {"id": "a", "route": "", "caption": "c"},
            {"id": "a b", "route": "#/en", "caption": "c"},
            {"id": "a", "route": "#/en", "caption": "c", "clip": "1,2,3"},
            {"id": "a", "route": "#/en", "caption": "c", "width": "wide"},
            {"id": "a", "route": "#/en", "caption": "c", "format": "gif"},
            {"id": "a", "route": "#/en", "caption": ""},
        ):
            with self.assertRaises(screenshots.ScreenshotError):
                screenshots.parse(params)

    def test_a_missing_picture_fails_the_build_and_a_moved_one_warns(self) -> None:
        document = _compile(self.HEAD + self._block())
        with tempfile.TemporaryDirectory() as workspace:
            directory = Path(workspace)
            problems = validate._check_screenshots(document, directory)
            self.assertEqual([problem.severity for problem in problems], ["error"])
            self.assertIn("--shots shot-one", problems[0].message)

            shot = screenshots.parse(document.mounts[0].params)
            (directory / shot.file_name).write_bytes(b"picture")
            screenshots.save_index(
                {
                    shot.id: screenshots.Capture(
                        id=shot.id,
                        file=shot.file_name,
                        fingerprint=shot.fingerprint,
                        captured="2026-01-01T00:00:00Z",
                    )
                },
                directory,
            )
            self.assertEqual(validate._check_screenshots(document, directory), [])

            moved = _compile(self.HEAD + self._block(route="#/de"))
            problems = validate._check_screenshots(moved, directory)
            self.assertEqual([problem.severity for problem in problems], ["warning"])
            self.assertIn("retake", problems[0].message)

    def test_two_blocks_may_not_claim_one_file(self) -> None:
        source = self.HEAD + self._block() + self._block(route="#/de")
        problems = validate._check_screenshots(_compile(source), Path("nowhere"))
        self.assertIn("already used", problems[0].message)

    def test_the_picture_reaches_the_page_inlined(self) -> None:
        """The report is one file; a figure beside it would travel only sometimes."""
        document = _compile(self.HEAD + self._block(format="png"))
        with tempfile.TemporaryDirectory() as workspace:
            directory = Path(workspace)
            shot = screenshots.parse(document.mounts[0].params)
            (directory / shot.file_name).write_bytes(b"\x89PNG\r\n")
            screenshots.save_index(
                {
                    shot.id: screenshots.Capture(
                        id=shot.id,
                        file=shot.file_name,
                        fingerprint=shot.fingerprint,
                        captured="2026-01-01T00:00:00Z",
                    )
                },
                directory,
            )
            embedded = screenshots.payload(screenshots.collect(document, directory))
        entry = embedded["shot-one"]
        self.assertEqual(entry["status"], "current")
        self.assertTrue(entry["src"].startswith("data:image/png;base64,"))
        self.assertIn(entry["route"], entry["declaration"])

    def test_the_manifest_says_everything_the_capture_script_reads(self) -> None:
        """Python owns the description; Node owns the browser. One contract."""
        shot = screenshots.parse({"id": "a", "route": "#/en", "caption": "c"})
        script = (SCRIPTS_DIR / "capture_report_screenshots.mjs").read_text(
            encoding="utf-8"
        )
        entry = screenshots.manifest([shot])["shots"][0]
        for key in entry:
            self.assertIn(
                f"shot.{key}",
                script,
                f"the manifest carries '{key}' and the capture script ignores it",
            )

    def test_the_report_ships_the_pictures_it_declares(self) -> None:
        codebase = scan_codebase()
        document = report.compile_report(
            REPORT_SOURCE.read_text(encoding="utf-8"),
            facts_module.collect(codebase),
        )
        album = screenshots.collect(document)
        self.assertTrue(album.shots, "the report declares no screenshot")
        for shot in album.shots:
            self.assertEqual(
                album.status(shot),
                "current",
                f"'{shot.id}' is {album.status(shot)}: run "
                f"'python scripts/generate_report.py --shots {shot.id}'",
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
        payload = build_payload(codebase, {})
        self.assertEqual(
            [part["id"] for part in payload["teaser"]["parts"]],
            teaser.part_ids(),
        )


class ConceptTests(unittest.TestCase):
    """The vocabulary the report speaks in, and the glyphs that carry it.

    Two things can go wrong quietly here and both mislead a reader rather than
    breaking a build: a mark that has drifted from the icon the application
    actually draws, and a path on disk resurfacing in a page that is supposed
    to talk about concepts.
    """

    def test_every_concept_has_a_glyph_the_application_would_draw(self) -> None:
        self.assertEqual(concepts.check_icons(), [])

    def test_every_artifact_names_a_concept(self) -> None:
        for artifact in spec.ARTIFACTS:
            self.assertIsNotNone(
                concepts.concept_by_id(artifact.concept),
                f"artifact '{artifact.id}' names unknown concept "
                f"'{artifact.concept}'",
            )

    def test_the_payload_carries_the_vocabulary_but_no_paths(self) -> None:
        payload = build_payload(scan_codebase(), {})
        self.assertEqual(
            [concept["id"] for concept in payload["concepts"]],
            concepts.concept_ids(),
        )
        for concept in payload["concepts"]:
            self.assertTrue(concept["path"], f"{concept['id']} has no icon path")
        for artifact in payload["artifacts"]:
            self.assertNotIn("path", artifact)

    def test_the_authored_layer_names_no_generated_data_path(self) -> None:
        """Everything the docs build writes itself speaks in concepts.

        Verbatim prompts and the docstrings lifted out of the generation
        scripts are exempt: those are the source quoted as it stands, and
        rewriting a quotation to avoid a filename would make it a paraphrase.
        """
        payload = build_payload(scan_codebase(), {})
        authored = json.dumps(
            [
                payload["artifacts"],
                payload["concepts"],
                payload["teaser"],
                payload["lanes"],
                payload["groups"],
                [step["spec_summary"] for step in payload["steps"]],
            ]
        )
        for needle in (
            "life_events.json",
            "ego_network.json",
            "persons.json",
            "meta_stories.json",
            "data/people/",
        ):
            self.assertNotIn(needle, authored)

    def test_a_referenced_part_carries_its_concept_glyph(self) -> None:
        document = _compile(
            "---\ntitle: T\n---\n\n## S\n\nAs [[graph|a social network]].\n"
        )
        self.assertIn('class="glyph"', document.html)
        self.assertIn(concepts.icon_of("network"), document.html)

    def test_a_part_without_a_concept_gets_no_glyph(self) -> None:
        document = _compile("---\ntitle: T\n---\n\n## S\n\nSee [[kinds|them]].\n")
        self.assertNotIn('class="glyph"', document.html)


class FactTests(unittest.TestCase):
    """A cited number is only worth citing if it was really measured."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = facts_module.collect(scan_codebase())

    def test_every_fact_has_a_display_value_and_a_source(self) -> None:
        self.assertTrue(self.facts)
        for key, fact in self.facts.items():
            self.assertEqual(key, fact.key)
            self.assertTrue(fact.display, f"{key} has no display value")
            self.assertTrue(fact.source, f"{key} does not say where it came from")

    def test_repository_measurements_are_not_silently_zero(self) -> None:
        """A directory listing that fails quietly would read as a real zero."""
        for key in ("app.languages", "pipeline.models"):
            self.assertGreater(self.facts[key].value or 0, 0, f"{key} measured nothing")

    def test_no_fact_is_an_inventory_count(self) -> None:
        """Facts name things; how many there are of them is not an argument.

        The report used to cite its own tallies—steps, layers, edges, schemas,
        artifacts—and a reader carried each number without ever being asked to
        use it. The figures show that shape better than a sentence can, so a
        citation that renders as a bare number is the thing this check exists
        to catch on the way back in.
        """
        for key, fact in self.facts.items():
            self.assertFalse(
                fact.display.isdigit(),
                f"{key} cites the count {fact.display}; cite what it is instead",
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


class LayoutWidthTests(unittest.TestCase):
    """Width is opt-in, and the opting has to reach the page.

    Nothing read as text is set wider than the measure, and extra width is spent
    only on figures that have something to do with it. That rule is split across
    three files—the roster here decides it, `_mount_html` writes it into the
    class, `style.css` acts on it—so each seam is checked: a component whose
    width nobody declares, a class nobody styles, or a margin column measured
    from a literal instead of from the measure would each break it silently.
    """

    KNOWN_WIDTHS = {"measure", "wide", "figure"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.css = (ASSETS / "style.css").read_text(encoding="utf-8")
        cls.js = (ASSETS / "app.js").read_text(encoding="utf-8")

    def test_every_component_declares_a_width_the_page_understands(self) -> None:
        for name, spec in report.COMPONENTS.items():
            self.assertIn(
                spec.width,
                self.KNOWN_WIDTHS,
                f"'{name}' claims width {spec.width!r}, which nothing styles",
            )

    def test_the_roster_writes_the_width_into_the_mount_point(self) -> None:
        wide = _compile(
            MarkdownCompilerTests.HEAD + "\n## S\n\n::: pipeline lane=person\n:::\n"
        )
        self.assertIn('class="widget widget-wide"', wide.html)

        measure = _compile(
            MarkdownCompilerTests.HEAD + "\n## S\n\n::: kindlegend\n:::\n"
        )
        self.assertIn('class="widget"', measure.html)
        self.assertNotIn("widget-wide", measure.html)

    def test_a_screenshot_is_left_for_the_renderer_to_classify(self) -> None:
        """Its width is the capture's, which only `app.js` has in front of it."""
        self.assertEqual(report.COMPONENTS["screenshot"].width, "figure")
        document = _compile(
            MarkdownCompilerTests.HEAD + "\n## S\n\n"
            '::: screenshot id=x route=#/en caption="A view."\n:::\n'
        )
        self.assertIn('class="widget"', document.html)
        self.assertIn("widget-margin", self.js)
        self.assertIn("widget-wide", self.js)

    def test_every_width_class_a_renderer_adds_is_styled(self) -> None:
        added = {
            name.strip()
            for name in report.WIDGET_WIDTH_CLASS.values()
            if name.strip()
        }
        added.update(re.findall(r'"(widget-[a-z-]+)"', self.js))
        self.assertIn("widget-margin", added, "the scan found no width classes")
        for name in sorted(added):
            self.assertRegex(
                self.css,
                rf"\.{name}[\s,{{]",
                f"a renderer adds .{name} and style.css has no rule for it",
            )

    def test_the_margin_column_is_whatever_the_measure_leaves(self) -> None:
        """Measured, not guessed: a literal here would drift off the text edge."""
        query = re.search(
            r"@container report \(width >= (\d+)px\) \{(.*?)\n\}",
            self.css,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(query, "the stylesheet declares no margin column")
        assert query is not None
        self.assertIn("100cqi", query.group(2))
        self.assertIn("var(--measure)", query.group(2))
        self.assertIn("var(--figure-gutter)", query.group(2))
        self.assertIn("container: report / inline-size", self.css)


class PrintTests(unittest.TestCase):
    """The printed report must be the whole report.

    A scrollbar is the screen's way of saying "there is more"; paper has no way
    of saying it, so a container that clips on screen and is neither reopened nor
    hidden for print silently drops whatever it was holding. The same goes for
    the step details: they reach paper only because the appendix is built from
    the very function that fills the drawer.
    """

    @classmethod
    def setUpClass(cls) -> None:
        css = (ASSETS / "style.css").read_text(encoding="utf-8")
        marker = "@media print {"
        index = css.index(marker)
        cls.screen_css = css[:index]
        cls.print_css = css[index:]
        cls.js = (ASSETS / "app.js").read_text(encoding="utf-8")

    @staticmethod
    def _rules(css: str) -> "list[tuple[str, str]]":
        """Flat (selector list, body) pairs, one per declaration block.

        Enough of a parser for this stylesheet: it nests only in at-rules, whose
        opening brace is dropped along with everything before it.
        """
        rules = []
        css = re.sub(r"/\*.*?\*/", " ", css, flags=re.DOTALL)
        for block in css.split("}"):
            if "{" not in block:
                continue
            head, body = block.rsplit("{", 1)
            selectors = head.split("{")[-1]
            rules.append((" ".join(selectors.split()), body))
        return rules

    def test_every_clipping_container_is_reopened_or_hidden_for_print(self) -> None:
        hidden = [
            part.strip()
            for selector, body in self._rules(self.print_css)
            if "display: none" in body
            for part in selector.split(",")
        ]
        self.assertIn(".rail", hidden, "the scan found no hidden chrome")

        clipped = [
            part.strip()
            for selector, body in self._rules(self.screen_css)
            if "overflow" in body and ("auto" in body or "hidden" in body)
            for part in selector.split(",")
        ]
        self.assertIn(".chart-scroll", clipped, "the scan found no scroll boxes")

        for selector in clipped:
            leaf = selector.split()[-1]
            # Either the print rules speak about it, or it lives inside
            # something they hide—which this stylesheet names as a prefix.
            covered = leaf in self.print_css or any(
                leaf.startswith(name) for name in hidden
            )
            self.assertTrue(
                covered,
                f"{selector} clips on screen but the print rules neither reopen "
                f"nor hide it: on paper what it holds is cut off, not scrolled to",
            )

    def test_a_margin_figure_does_not_float_on_paper(self) -> None:
        """A sheet has no margin column, and nothing on paper clears a float."""
        floats = [
            body
            for selector, body in self._rules(self.print_css)
            if "widget-margin" in selector
        ]
        self.assertTrue(floats, "the print rules say nothing about a margin figure")
        for body in floats:
            self.assertIn("float: none", body)

    def test_the_appendix_is_the_drawer(self) -> None:
        """One builder, so a new fact in the drawer reaches the PDF for free."""
        self.assertIn("function stepDetail(", self.js)
        self.assertIn("stepDetail(body, step, false)", self.js)  # the drawer
        self.assertIn("stepDetail(body, step, true)", self.js)  # the appendix
        self.assertIn("renderStepAppendix();", self.js)

    def test_the_export_script_waits_for_the_page_to_finish(self) -> None:
        """Printing a half-hydrated page yields a report of empty figures."""
        script = (SCRIPTS_DIR / "export_report_pdf.mjs").read_text(encoding="utf-8")
        self.assertIn("data-report-ready", script)
        self.assertIn("data-report-ready", self.js)


if __name__ == "__main__":
    unittest.main()
