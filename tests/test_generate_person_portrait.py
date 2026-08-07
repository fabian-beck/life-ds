from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import generate_person_portrait as portraits  # noqa: E402


def _response(content: bytes, content_type: str) -> Mock:
    response = Mock()
    response.headers = {"Content-Type": content_type}
    response.content = content
    response.raise_for_status.return_value = None
    response.iter_content.return_value = [content]
    return response


class PortraitPipelineTests(unittest.TestCase):
    def test_architectuul_uses_uncropped_lead_image(self) -> None:
        page = b"""<html><head><meta property='og:image' content='https://example/1200x630.jpg'></head>
        <body><section class='lead'><div data-image-src='https://example/1312x.jpg'></div></section></body></html>"""
        with patch.object(
            portraits.requests, "get", return_value=_response(page, "text/html")
        ):
            image_url, source_url = portraits.extract_image_from_page(
                "https://architectuul.com/architect/geoffrey-bawa"
            )
        self.assertEqual(image_url, "https://example/1312x.jpg")
        self.assertEqual(source_url, "https://architectuul.com/architect/geoffrey-bawa")

    def test_download_image_decodes_reference_before_accepting(self) -> None:
        output = Path("reference.jpg")
        image_context = Mock()
        image_context.__enter__ = Mock(return_value=Mock())
        image_context.__exit__ = Mock(return_value=False)
        with (
            patch.object(
                portraits.requests,
                "get",
                return_value=_response(b"valid-image-bytes", "image/jpeg"),
            ),
            patch("builtins.open", mock_open()) as opened,
            patch.object(
                portraits.Image, "open", return_value=image_context
            ) as decoded,
            patch.object(Path, "mkdir"),
        ):
            self.assertTrue(
                portraits.download_image("https://example/reference.jpg", output)
            )
        opened.assert_called_once_with(output, "wb")
        decoded.assert_called_once_with(output)
        image_context.__enter__.return_value.verify.assert_called_once_with()

    def test_download_image_rejects_html_disguised_as_image(self) -> None:
        output = Path("reference.jpg")
        with (
            patch.object(
                portraits.requests,
                "get",
                return_value=_response(b"<html>not an image</html>", "text/html"),
            ),
            patch.object(portraits.time, "sleep"),
        ):
            self.assertFalse(
                portraits.download_image(
                    "https://example/reference.jpg", output, max_retries=1
                )
            )


if __name__ == "__main__":
    unittest.main()
