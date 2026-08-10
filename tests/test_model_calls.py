"""The shared model call: what it retries, and what it says when it gives up.

Every phase reaches the API through ``parse_structured``, so its retry policy
is the pipeline's retry policy. The distinction it draws is between a failure
that a second identical request could survive — a dropped connection, a rate
limit, a 502 — and one it cannot: a malformed request is malformed on the third
attempt too, and a refusal is an answer rather than an outage.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pydantic import BaseModel  # noqa: E402

from utils import model_calls  # noqa: E402
from utils.model_calls import parse_structured  # noqa: E402


class Answer(BaseModel):
    value: str


def _status_error(code: int) -> model_calls.APIStatusError:
    return model_calls.APIStatusError(
        f"status {code}", response=Mock(status_code=code, headers={}), body=None
    )


def _client(*responses) -> Mock:
    client = Mock()
    client.responses.parse.side_effect = list(responses)
    return client


def _ok(value: str = "ok") -> Mock:
    return Mock(status="completed", output_parsed=Answer(value=value))


def _empty() -> Mock:
    return Mock(status="completed", output_parsed=None, output=[], error=None)


def _refused(text: str = "I can't help with that") -> Mock:
    return Mock(
        status="completed",
        output_parsed=None,
        output=[Mock(content=[Mock(refusal=text)])],
        error=None,
    )


def _call(client: Mock, **kwargs):
    return parse_structured(
        client,
        model="gpt-test",
        reasoning_effort="low",
        input=[{"role": "user", "content": "prompt"}],
        text_format=Answer,
        label="a phase",
        **kwargs,
    )


class RetryClassificationTests(unittest.TestCase):
    def test_transient_conditions_are_retryable(self) -> None:
        for code in (408, 409, 429, 500, 502, 503, 504):
            with self.subTest(code=code):
                self.assertTrue(model_calls.is_retryable(_status_error(code)))
        self.assertTrue(
            model_calls.is_retryable(model_calls.APIConnectionError(request=Mock()))
        )

    def test_a_request_the_service_rejected_is_not_retryable(self) -> None:
        for code in (400, 401, 403, 404, 422):
            with self.subTest(code=code):
                self.assertFalse(model_calls.is_retryable(_status_error(code)))

    def test_an_ordinary_bug_is_not_retryable(self) -> None:
        """A TypeError in our own argument building is not an outage."""
        self.assertFalse(model_calls.is_retryable(TypeError("bad argument")))


class ParseStructuredTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.object(model_calls.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_parsed_answer_is_returned(self) -> None:
        client = _client(_ok("yes"))
        result = _call(client)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.value, "yes")

    def test_a_transient_failure_is_retried_with_widening_delay(self) -> None:
        client = _client(_status_error(503), _status_error(429), _ok())
        self.assertIsNotNone(_call(client))
        self.assertEqual(client.responses.parse.call_count, 3)
        self.assertEqual(
            [call.args[0] for call in self.sleep.call_args_list],
            [model_calls.BACKOFF_SECONDS, model_calls.BACKOFF_SECONDS * 2],
        )

    def test_retries_are_bounded_by_attempts(self) -> None:
        client = _client(*[_status_error(500)] * 5)
        self.assertIsNone(_call(client, attempts=2))
        self.assertEqual(client.responses.parse.call_count, 2)

    def test_a_rejected_request_ends_the_call_at_once(self) -> None:
        client = _client(_status_error(400), _ok())
        self.assertIsNone(_call(client))
        self.assertEqual(client.responses.parse.call_count, 1)

    def test_a_refusal_ends_the_call_at_once(self) -> None:
        """A refusal is the model's answer, not a failure to reach it."""
        client = _client(_refused(), _ok())
        self.assertIsNone(_call(client))
        self.assertEqual(client.responses.parse.call_count, 1)

    def test_an_empty_response_is_retried(self) -> None:
        """Nothing parsed and nothing refused is the case a retry can fix."""
        client = _client(_empty(), _ok("second time"))
        result = _call(client)
        assert result is not None
        self.assertEqual(result.value, "second time")
        self.assertEqual(client.responses.parse.call_count, 2)

    def test_the_effort_is_always_sent(self) -> None:
        """The setting the six migrated call sites used to omit entirely."""
        client = _client(_ok())
        _call(client)
        kwargs = client.responses.parse.call_args.kwargs
        self.assertEqual(kwargs["reasoning"], {"effort": "low"})
        self.assertEqual(kwargs["model"], "gpt-test")
        self.assertIs(kwargs["text_format"], Answer)

    def test_the_label_names_the_phase_in_the_failure(self) -> None:
        client = _client(_status_error(400))
        with patch("builtins.print") as printed:
            _call(client)
        said = " ".join(str(call.args[0]) for call in printed.call_args_list)
        self.assertIn("a phase", said)


class ParseStructuredOrRaiseTests(unittest.TestCase):
    """The variant for phases that must stop rather than write a stub.

    Curation cannot absorb a ``None``: a dataset with no events, or a review
    that reports nothing, would be written to disk and read later as a
    finding. These phases raised before the wrapper existed and still do.
    """

    def setUp(self) -> None:
        patcher = patch.object(model_calls.time, "sleep")
        self.slept = patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self, client: Mock):
        return model_calls.parse_structured_or_raise(
            client,
            model="gpt-test",
            reasoning_effort="low",
            input=[{"role": "user", "content": "hello"}],
            text_format=Answer,
            label="a phase",
        )

    def test_a_parsed_answer_is_returned_unwrapped(self) -> None:
        self.assertEqual(self._call(_client(_ok("yes"))).value, "yes")

    def test_giving_up_raises_rather_than_returning_none(self) -> None:
        with patch("builtins.print"):
            with self.assertRaises(model_calls.ModelCallFailed):
                self._call(_client(_status_error(400)))

    def test_the_reason_travels_with_the_exception(self) -> None:
        # The log line is far from where a caller reports the failure, so the
        # exception has to carry the phase and the cause on its own.
        with patch("builtins.print"):
            with self.assertRaises(model_calls.ModelCallFailed) as caught:
                self._call(_client(_refused("I can't help with that")))
        message = str(caught.exception)
        self.assertIn("a phase", message)
        self.assertIn("refused", message)

    def test_it_retries_before_it_raises(self) -> None:
        # The point of routing these sites through the wrapper: a rate limit
        # mid-run used to kill the phase outright.
        client = _client(_status_error(429), _ok("recovered"))
        with patch("builtins.print"):
            self.assertEqual(self._call(client).value, "recovered")
        self.assertEqual(client.responses.parse.call_count, 2)

    def test_it_is_a_runtime_error_for_callers_that_still_catch_one(self) -> None:
        self.assertTrue(issubclass(model_calls.ModelCallFailed, RuntimeError))


if __name__ == "__main__":
    unittest.main()
