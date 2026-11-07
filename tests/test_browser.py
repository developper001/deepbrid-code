from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from src.browser import DeepbridChatBrowser


class FakeWebSocket:
    def __init__(self) -> None:
        self.commands: list[dict[str, object]] = []
        self.closed = False

    def send(self, message: str) -> None:
        self.commands.append(json.loads(message))

    def recv(self) -> str:
        command = self.commands[-1]
        results = {
            "DOM.getDocument": {"root": {"nodeId": 10}},
            "DOM.querySelector": {"nodeId": 20},
            "DOM.setFileInputFiles": {},
        }
        return json.dumps(
            {
                "id": command["id"],
                "result": results[str(command["method"])],
            }
        )

    def close(self) -> None:
        self.closed = True


class BrowserImageUploadTests(unittest.TestCase):
    def test_image_upload_uses_one_connection_for_dom_node_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            image = project / "screenshot.png"
            image.write_bytes(b"image data")
            connection = FakeWebSocket()
            browser = DeepbridChatBrowser(project / "profile")

            with (
                patch(
                    "src.browser.websocket.create_connection",
                    return_value=connection,
                ) as create_connection,
                patch.object(
                    browser,
                    "_evaluate",
                    side_effect=[
                        {"readyNames": ["screenshot.png"]},
                        {"readyNames": ["screenshot.png"], "failedNames": []},
                    ],
                ) as evaluate,
            ):
                browser._attach_images(
                    "ws://127.0.0.1:9222/devtools/page/test",
                    [image],
                    project,
                )

            create_connection.assert_called_once()
            self.assertEqual(evaluate.call_count, 2)
            self.assertTrue(connection.closed)
            self.assertEqual(
                [command["method"] for command in connection.commands],
                [
                    "DOM.getDocument",
                    "DOM.querySelector",
                    "DOM.setFileInputFiles",
                ],
            )
            self.assertEqual([command["id"] for command in connection.commands], [1, 2, 3])
            self.assertEqual(
                connection.commands[1]["params"],
                {
                    "nodeId": 10,
                    "selector": 'input[type="file"][accept*="image/"]',
                },
            )
            self.assertEqual(
                connection.commands[2]["params"],
                {"nodeId": 20, "files": [str(image.resolve())]},
            )

    def test_attachment_wait_requires_all_requested_files_ready(self) -> None:
        browser = DeepbridChatBrowser(Path("profile"))
        with patch.object(
            browser,
            "_evaluate",
            side_effect=[
                {"readyNames": ["existing.png"], "failedNames": []},
                {
                    "readyNames": ["existing.png", "new.png"],
                    "failedNames": [],
                },
            ],
        ) as evaluate:
            browser._wait_for_image_attachments(
                "ws://127.0.0.1:9222/devtools/page/test",
                Counter({"existing.png": 1, "new.png": 1}),
            )
        self.assertEqual(evaluate.call_count, 2)

    def test_submission_wait_reports_if_prompt_was_not_accepted(self) -> None:
        browser = DeepbridChatBrowser(Path("profile"))
        with (
            patch.object(
                browser,
                "_evaluate",
                return_value={"accepted": False},
            ),
            patch("src.browser.time.monotonic", side_effect=[0, 6]),
            patch("src.browser.time.sleep"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "did not accept the message",
            ):
                browser._wait_for_submission(
                    "ws://127.0.0.1:9222/devtools/page/test",
                    0,
                )
