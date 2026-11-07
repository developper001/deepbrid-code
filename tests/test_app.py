from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from src.app import DeepbridCodeApp
from src.settings import AUTO_OPEN_CHROME, LAST_PROJECT, SettingsStore


class AppStartupTests(unittest.TestCase):
    def test_startup_reopens_saved_project_and_honors_disabled_chrome_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            project.mkdir()
            (project / "main.py").write_text("print('saved')", encoding="utf-8")
            store = SettingsStore(root_path / "settings.sqlite3")
            store.set(LAST_PROJECT, str(project))
            store.set_bool(AUTO_OPEN_CHROME, False)

            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", store.database_path),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch.object(DeepbridCodeApp, "_start_browser_open") as open_browser,
                ):
                    app = DeepbridCodeApp(root)
                    app._startup()

                self.assertEqual(app.project_root, project.resolve())
                self.assertEqual(len(app.tree_paths), 1)
                self.assertFalse(app.auto_open_chrome)
                open_browser.assert_not_called()
            finally:
                root.destroy()

    def test_startup_opens_chrome_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            database = root_path / "settings.sqlite3"
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", database),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch.object(DeepbridCodeApp, "_start_browser_open") as open_browser,
                ):
                    app = DeepbridCodeApp(root)
                    app._startup()

                self.assertTrue(app.auto_open_chrome)
                open_browser.assert_called_once_with(startup=True)
            finally:
                root.destroy()

    def test_send_submits_directly_without_a_confirmation_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app.auto_open_chrome = False
                    app.message.insert("1.0", "What is 3 minus 1?")
                    with (
                        patch("src.app.threading.Thread") as thread,
                        patch("src.app.tk.Toplevel", side_effect=AssertionError("unexpected dialog")),
                    ):
                        app._send()

                thread.assert_called_once()
                thread.return_value.start.assert_called_once()
                self.assertTrue(app.chat_request_active)
                self.assertEqual(app.status.get(), "Sending message to Deepbrid AI Chat. Waiting for its response...")
                self.assertIn("What is 3 minus 1?", app.chat_output.get("1.0", "end"))
                self.assertEqual(app.message.get("1.0", "end-1c"), "")
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main()
