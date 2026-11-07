from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src.app import DeepbridCodeApp
from src.settings import AUTO_OPEN_CHROME, DARK_THEME, LAST_PROJECT, WRAP_TEXT, SettingsStore
from src.settings_dialog import SettingsDialog


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

    def test_dark_theme_is_restored_and_progress_is_hidden_when_idle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            store = SettingsStore(root_path / "settings.sqlite3")
            store.set_bool(DARK_THEME, True)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", store.database_path),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    self.assertTrue(app.dark_theme)
                    self.assertTrue(app.wrap_text)
                    self.assertEqual((app.logo_image.width(), app.logo_image.height()), (48, 48))
                    self.assertEqual(
                        [icon.width() for icon in app.window_icons],
                        [16, 32, 48],
                    )
                    self.assertEqual(app.preview.cget("background"), "#171c19")
                    self.assertFalse(app.progress.winfo_manager())

                    app._start_progress()
                    self.assertEqual(app.progress.winfo_manager(), "pack")
                    app._stop_progress()
                    self.assertFalse(app.progress.winfo_manager())
            finally:
                root.destroy()

    def test_wrap_setting_persists_and_controls_preview_wrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            store = SettingsStore(root_path / "settings.sqlite3")
            store.set_bool(WRAP_TEXT, False)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", store.database_path),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    self.assertFalse(app.wrap_text)
                    self.assertEqual(app.preview.cget("wrap"), "none")
                    app._set_wrap_text(True)
                    self.assertTrue(app.wrap_text)
                    self.assertEqual(app.preview.cget("wrap"), "word")
            finally:
                root.destroy()

    def test_project_file_context_menu_adds_the_selected_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            project.mkdir()
            (project / "main.py").write_text("print('hello')", encoding="utf-8")
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._load_project(project)
                    item = "f:main.py"
                    event = SimpleNamespace(y=10, x_root=20, y_root=30)
                    with (
                        patch.object(app.file_tree, "identify_row", return_value=item),
                        patch.object(app.file_context_menu, "tk_popup") as popup,
                    ):
                        self.assertEqual(app._show_file_context_menu(event), "break")
                    self.assertEqual(app.file_tree.selection(), (item,))
                    popup.assert_called_once_with(20, 30)

                    app.file_context_menu.invoke(0)
                    self.assertEqual(len(app.context_files), 1)
                    self.assertIn("main.py (text)", app.context_list.get(0))
                    self.assertIn("Added main.py", app.status.get())
            finally:
                root.destroy()

    def test_add_context_button_includes_the_selected_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            project.mkdir()
            (project / "main.py").write_text("print('hello')", encoding="utf-8")
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._load_project(project)
                    app.file_tree.selection_set("f:main.py")
                    app.add_context_button.invoke()

                    self.assertEqual(len(app.context_files), 1)
                    self.assertEqual(app.context_list.size(), 1)
                    self.assertIn("main.py (text)", app.context_list.get(0))
                    self.assertIn("Added main.py", app.status.get())
            finally:
                root.destroy()

    def test_add_context_button_explains_that_folders_are_not_context_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            source = project / "src"
            source.mkdir(parents=True)
            (source / "main.py").write_text("print('hello')", encoding="utf-8")
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._load_project(project)
                    app.file_tree.selection_set("d:src")
                    app.add_context_button.invoke()

                    self.assertEqual(len(app.context_files), 0)
                    self.assertIn("src (folder)", app.status.get())
                    self.assertIn("Skipped unsupported item", app.status.get())
            finally:
                root.destroy()

    def test_pasting_clipboard_image_adds_visible_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch("src.app.ImageGrab.grabclipboard", return_value=Image.new("RGB", (4, 4), "red")),
                ):
                    app = DeepbridCodeApp(root)
                    result = app._paste_clipboard_image(SimpleNamespace())

                    self.assertEqual(result, "break")
                    self.assertEqual(len(app.context_files), 1)
                    item = next(iter(app.context_files.values()))
                    self.assertEqual(item.kind, "image")
                    self.assertTrue(item.external)
                    self.assertTrue(item.path.is_file())
                    self.assertIn("Clipboard image 1 (image)", app.context_list.get(0))
                    self.assertIn("Added clipboard-1.png", app.status.get())
                    app._cleanup_clipboard_images()
                    self.assertIsNone(app.clipboard_image_directory)
            finally:
                root.destroy()

    def test_settings_dialog_persists_dark_theme_changes(self) -> None:
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
                    dialog = SettingsDialog(
                        root,
                        app.settings,
                        app.auto_open_chrome,
                        app._set_auto_open_chrome,
                        app.dark_theme,
                        app._set_dark_theme,
                        app.wrap_text,
                        app._set_wrap_text,
                    )
                    dialog.dark_theme.set(True)
                    dialog._save_dark_theme()
                    dialog.wrap_text.set(False)
                    dialog._save_wrap_text()

                self.assertTrue(app.dark_theme)
                self.assertTrue(app.settings.get_bool(DARK_THEME, default=False))
                self.assertFalse(app.settings.get_bool(WRAP_TEXT, default=True))
                self.assertFalse(app.wrap_text)
                self.assertEqual(dialog.status.get(), "Saved.")
                dialog.dialog.destroy()
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
