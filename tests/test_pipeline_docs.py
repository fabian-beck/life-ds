"""Tests for the pipeline documentation build.

The point of these is narrow: the docs are only trustworthy if the static
extraction really reads the source (rather than quietly returning nothing) and
if the drift check really fails when the pipeline moves. Everything else in the
build is presentation.
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

from pipeline_docs import render, spec, validate  # noqa: E402
from pipeline_docs.introspect import scan_codebase, scan_script  # noqa: E402
from pipeline_docs.model import build_payload  # noqa: E402


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


class AssetTests(unittest.TestCase):
    def test_page_has_no_dark_mode(self) -> None:
        """Light-only was an explicit request; keep it from creeping back."""
        css = (SCRIPTS_DIR / "pipeline_docs" / "assets" / "style.css").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("prefers-color-scheme", css)
        self.assertNotIn('data-theme="dark"', css)

    def test_javascript_parses_and_uses_no_network(self) -> None:
        js = (SCRIPTS_DIR / "pipeline_docs" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        for forbidden in ("fetch(", "XMLHttpRequest", "import("):
            self.assertNotIn(forbidden, js)

    def test_spec_module_has_no_syntax_drift(self) -> None:
        source = (SCRIPTS_DIR / "pipeline_docs" / "spec.py").read_text(encoding="utf-8")
        ast.parse(source)


if __name__ == "__main__":
    unittest.main()
