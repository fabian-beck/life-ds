"""The portrait pick gets looked at, and its metadata follows the original.

Two defects this guards against. The matcher chooses the reference portrait
from filenames and captions alone, and nothing downstream checked the choice —
with Openverse in the candidate pool, a photograph of the subject's spouse
carries the subject's name in its caption. And when a generated portrait was
preserved, only `originalImage` was swapped: `source` kept pointing at
wherever a previous original came from, and the new original's attribution
was dropped entirely.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from events.images.assign import (  # noqa: E402
    PortraitVerification,
    verify_portrait_depicts_person,
)
from generate_person_events import resolve_portrait  # noqa: E402

PORTRAIT = {
    "url": "https://images.example.org/wagner_1915.jpg",
    "caption": "Otto Wagner (1915)",
    "filename": "wagner_1915.jpg",
    "source": "https://www.rawpixel.com/image/11681386",
    "creator": "Austrian National Library",
    "license": "CC0 1.0",
    "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
}

GENERATED = {
    "image": "/portraits/otto_wagner_thumbnail.webp",
    "thumbnail": "/portraits/otto_wagner_thumbnail.webp",
    "medium": "/portraits/otto_wagner_medium.webp",
    "full": "/portraits/otto_wagner_full.webp",
    "source": "https://de.wikipedia.org/wiki/Otto_Wagner",
    "caption": "Stylized portrait based on historical photograph",
    "creator": "AI generated artwork",
    "originalImage": "https://upload.wikimedia.org/old_original.jpg",
}


def _verify(parsed):
    with (
        patch("events.images.assign.get_client"),
        patch("events.images.assign.parse_structured", return_value=parsed) as call,
    ):
        verdict = verify_portrait_depicts_person(PORTRAIT, "Otto Wagner")
    return verdict, call


class VerificationTests(unittest.TestCase):
    def test_a_yes_keeps_the_pick(self) -> None:
        verdict, _ = _verify(PortraitVerification(depicts_subject=True, reason="Him."))
        self.assertIs(verdict, True)

    def test_a_no_rejects_the_pick(self) -> None:
        verdict, _ = _verify(
            PortraitVerification(depicts_subject=False, reason="His wife Louise.")
        )
        self.assertIs(verdict, False)

    def test_a_failed_call_stays_undecided(self) -> None:
        verdict, _ = _verify(None)
        self.assertIsNone(verdict)

    def test_the_model_is_shown_the_image_and_the_name(self) -> None:
        _, call = _verify(PortraitVerification(depicts_subject=True, reason="Him."))
        (message,) = call.call_args.kwargs["input"]
        parts = {part["type"]: part for part in message["content"]}
        self.assertEqual(parts["input_image"]["image_url"], PORTRAIT["url"])
        self.assertIn("Otto Wagner", parts["input_text"]["text"])


class PortraitDataTests(unittest.TestCase):
    def test_preserved_portrait_keeps_the_artwork_and_follows_the_original(
        self,
    ) -> None:
        data = resolve_portrait(PORTRAIT, GENERATED)
        assert data is not None
        self.assertEqual(data["image"], GENERATED["image"])
        self.assertEqual(data["creator"], "AI generated artwork")
        self.assertEqual(data["originalImage"], PORTRAIT["url"])
        self.assertEqual(data["source"], PORTRAIT["source"])
        self.assertEqual(data["originalCreator"], PORTRAIT["creator"])
        self.assertEqual(data["originalLicense"], PORTRAIT["license"])
        self.assertEqual(data["originalLicenseUrl"], PORTRAIT["licenseUrl"])

    def test_stale_original_attribution_does_not_survive_a_swap(self) -> None:
        generated = {**GENERATED, "originalCreator": "Somebody Else"}
        bare = {k: v for k, v in PORTRAIT.items() if k in ("url", "source")}
        data = resolve_portrait(bare, generated)
        assert data is not None
        self.assertNotIn("originalCreator", data)

    def test_without_a_generated_portrait_the_selection_is_the_portrait(self) -> None:
        data = resolve_portrait(PORTRAIT, None)
        assert data is not None
        self.assertEqual(data["image"], PORTRAIT["url"])
        self.assertEqual(data["source"], PORTRAIT["source"])
        self.assertEqual(data["creator"], PORTRAIT["creator"])
        self.assertNotIn("originalImage", data)


if __name__ == "__main__":
    unittest.main()
