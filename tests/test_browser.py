from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.browser import AI_CHAT_URL, BrowserLaunchError, DeepbridChatBrowser


class BrowserTests(unittest.TestCase):
    def test_launch_uses_dedicated_profile_and_loopback_debugger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory) / "chrome-profile"
            with (
                patch.object(DeepbridChatBrowser, "_find_chrome", return_value="C:/Chrome/chrome.exe"),
                patch.object(DeepbridChatBrowser, "_debug_port", return_value=None),
                patch.object(DeepbridChatBrowser, "_find_free_port", return_value=9225),
                patch("src.browser.subprocess.Popen") as popen,
            ):
                DeepbridChatBrowser(profile).open()

            arguments = popen.call_args.args[0]
            self.assertIn(f"--user-data-dir={profile}", arguments)
            self.assertIn("--remote-debugging-port=9225", arguments)
            self.assertIn("--remote-debugging-address=127.0.0.1", arguments)
            self.assertEqual(arguments[-1], AI_CHAT_URL)
            self.assertTrue(profile.is_dir())
            self.assertEqual((profile / "DeepbridDevToolsPort").read_text(), "9225")

    def test_missing_chrome_is_reported(self) -> None:
        with (
            patch.object(DeepbridChatBrowser, "_find_chrome", return_value=None),
            self.assertRaisesRegex(BrowserLaunchError, "Google Chrome was not found"),
        ):
            DeepbridChatBrowser(Path("unused")).open()

    def test_target_selection_accepts_only_the_deepbrid_chat_page(self) -> None:
        browser = DeepbridChatBrowser(Path("unused"))
        targets = [
            {
                "type": "page",
                "url": "https://example.com/ai-chat",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/wrong",
            },
            {
                "type": "page",
                "url": "https://www.deepbrid.com/login",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/login",
            },
            {
                "type": "page",
                "url": "https://www.deepbrid.com/ai-chat?c=1",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/chat",
            },
            {
                "type": "page",
                "url": "https://www.deepbrid.com/ai-chat?c=2",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9999/devtools/page/wrong-port",
            },
            {
                "type": "page",
                "url": "https://[malformed",
                "webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/malformed",
            },
        ]
        with patch(
            "src.browser.urllib.request.urlopen",
            return_value=io.BytesIO(json.dumps(targets).encode("utf-8")),
        ):
            target = browser._find_chat_target(9225)

        self.assertEqual(
            target,
            {"webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/chat"},
        )

    def test_message_uses_visible_page_ui_and_returns_rendered_reply(self) -> None:
        browser = DeepbridChatBrowser(Path("unused"))
        with (
            patch.object(browser, "_wait_for_debug_port", return_value=9225),
            patch.object(
                browser,
                "_find_chat_target",
                return_value={"webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/one"},
            ),
            patch.object(browser, "_attach_images") as attach_images,
            patch.object(
                browser,
                "_evaluate",
                side_effect=[
                    {"ready": True},
                    {"sent": True, "assistantCount": 2},
                    {"assistantCount": 3, "busy": False, "response": "The answer."},
                ],
            ) as evaluate,
        ):
            result = browser.send_message("Explain the selected code.")

        self.assertEqual(result, "The answer.")
        attach_images.assert_called_once_with(
            "ws://127.0.0.1:9225/devtools/page/one",
            [],
            None,
        )
        self.assertIn("textarea[aria-label", evaluate.call_args_list[0].args[1])
        self.assertIn("Explain the selected code.", evaluate.call_args_list[1].args[1])
        self.assertIn(".dfy-msg-asst", evaluate.call_args_list[2].args[1])

    def test_send_navigates_existing_deepbrid_page_to_chat_after_login(self) -> None:
        browser = DeepbridChatBrowser(Path("unused"))
        with (
            patch.object(browser, "_wait_for_debug_port", return_value=9225),
            patch.object(browser, "_find_chat_target", return_value=None),
            patch.object(
                browser,
                "_navigate_to_chat",
                return_value={"webSocketDebuggerUrl": "ws://127.0.0.1:9225/devtools/page/one"},
            ) as navigate,
            patch.object(browser, "_attach_images"),
            patch.object(
                browser,
                "_evaluate",
                side_effect=[
                    {"ready": True},
                    {"sent": True, "assistantCount": 1},
                    {"assistantCount": 2, "busy": False, "response": "Done."},
                ],
            ),
        ):
            self.assertEqual(browser.send_message("Hello"), "Done.")

        navigate.assert_called_once_with(9225)

    def test_selected_images_are_attached_through_the_chat_file_input(self) -> None:
        browser = DeepbridChatBrowser(Path("unused"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "diagram.png"
            image.write_bytes(b"image")
            with patch.object(
                browser,
                "_send_command",
                side_effect=[
                    {"root": {"nodeId": 1}},
                    {"nodeId": 2},
                    {},
                ],
            ) as send_command:
                browser._attach_images(
                    "ws://127.0.0.1:9225/devtools/page/one",
                    [image],
                    root,
                )

        calls = send_command.call_args_list
        self.assertEqual(calls[0].args[1], "DOM.getDocument")
        self.assertEqual(calls[1].args[2]["selector"], 'input[type="file"][accept*="image/"]')
        self.assertEqual(calls[2].args[1], "DOM.setFileInputFiles")
        self.assertEqual(calls[2].args[2]["files"], [str(image)])

    def test_devtools_refuses_non_loopback_connection(self) -> None:
        with self.assertRaisesRegex(BrowserLaunchError, "non-local Chrome DevTools"):
            DeepbridChatBrowser._send_command(
                "ws://example.com:9225/devtools/page/one",
                "Runtime.evaluate",
                {"expression": "location.origin"},
            )


if __name__ == "__main__":
    unittest.main()
