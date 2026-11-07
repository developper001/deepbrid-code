from __future__ import annotations

import json
import tempfile
import unittest
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

            with patch(
                "src.browser.websocket.create_connection",
                return_value=connection,
            ) as create_connection:
                browser._attach_images(
                    "ws://127.0.0.1:9222/devtools/page/test",
                    [image],
                    project,
                )

            create_connection.assert_called_once()
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
