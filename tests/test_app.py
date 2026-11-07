from __future__ import annotations

import re
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src.app import DeepbridCodeApp
from src.context import build_prompt
from src.settings import (
    AUTO_OPEN_CHROME,
    DARK_THEME,
    LAST_PROJECT,
    OUTPUT_LOG_PATH,
    WRAP_TEXT,
    SettingsStore,
)
from src.settings_dialog import SettingsDialog


class AppStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.browser_start_patcher = patch.object(
            DeepbridCodeApp,
            "_start_browser_open",
        )
        self.browser_start_patcher.start()

    def tearDown(self) -> None:
        self.browser_start_patcher.stop()

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
                    self.assertTrue(root.geometry().startswith("1180x760"))
                    self.assertEqual(app.chat_output.cget("height"), 20)
                    self.assertEqual(app.message.cget("height"), 7)
                    self.assertEqual(app.file_tree.cget("height"), 10)
                    self.assertEqual(app.file_tree.master.grid_rowconfigure(1, "weight"), 0)
                    self.assertEqual(app.file_tree.master.grid_rowconfigure(4, "weight"), 1)
                    self.assertEqual(app.console_toggle_button.cget("text"), "Toggle Console")
                    self.assertEqual(app.send_button.cget("text"), "Send")
                    self.assertEqual(app.send_button.pack_info()["side"], "right")
                    with patch.object(app.main_pane, "winfo_height", return_value=600):
                        app._size_project_tree(SimpleNamespace())
                    self.assertEqual(app.file_tree.master.grid_rowconfigure(1, "minsize"), 270)
                    self.assertEqual((app.logo_image.width(), app.logo_image.height()), (48, 48))
                    self.assertEqual(
                        [icon.width() for icon in app.window_icons],
                        [16, 32, 48],
                    )
                    self.assertEqual(app.preview.cget("background"), "#171c19")
                    self.assertFalse(app.progress.winfo_manager())
                    app._initial_sash_set = False
                    with (
                        patch.object(app.main_pane, "winfo_width", return_value=1200),
                        patch.object(app.main_pane, "sashpos") as set_sash,
                    ):
                        app._size_initial_panes(SimpleNamespace())
                    set_sash.assert_called_once_with(0, 300)
                    self.assertFalse(hasattr(app, "add_context_button"))
                    self.assertFalse(hasattr(app, "remove_context_button"))

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
                    self.assertEqual(app.file_tree.item(item, "text"), "* main.py")
                    self.assertIn("Added main.py", app.status.get())
            finally:
                root.destroy()

    def test_right_click_context_menu_adds_and_removes_file(self) -> None:
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
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    self.assertEqual(app.file_context_menu.index("end"), 0)
                    self.assertEqual(
                        app.file_context_menu.entrycget(0, "label"),
                        "Add selected to context",
                    )
                    app.file_context_menu.invoke(0)

                    self.assertEqual(len(app.context_files), 1)
                    self.assertEqual(app.file_tree.item("f:main.py", "text"), "* main.py")
                    self.assertIn("Added main.py", app.status.get())

                    with (
                        patch.object(app.file_tree, "identify_row", return_value=item),
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    self.assertEqual(app.file_context_menu.index("end"), 1)
                    self.assertEqual(
                        app.file_context_menu.entrycget(1, "label"),
                        "Remove selected from context",
                    )
                    app.file_context_menu.invoke(1)
                    self.assertEqual(len(app.context_files), 0)
                    self.assertEqual(app.file_tree.item("f:main.py", "text"), "main.py")
                    self.assertFalse(hasattr(app, "add_context_button"))
                    self.assertFalse(hasattr(app, "remove_context_button"))
            finally:
                root.destroy()

    def test_directory_context_adds_text_files_and_ignores_non_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            source = project / "src"
            nested = source / "nested"
            nested.mkdir(parents=True)
            (source / "main.py").write_text("print('hello')", encoding="utf-8")
            (nested / "README").write_text("read me", encoding="utf-8")
            (source / "asset.bin").write_bytes(b"\x00\x01\xff")
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._load_project(project)
                    item = "d:src"
                    event = SimpleNamespace(y=10, x_root=20, y_root=30)
                    with (
                        patch.object(app.file_tree, "identify_row", return_value=item),
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    app.file_context_menu.invoke(0)

                    self.assertEqual(len(app.context_files), 2)
                    self.assertEqual(
                        {context.label for context in app.context_files.values()},
                        {"src/main.py", "src/nested/README"},
                    )
                    self.assertIn("Ignored 1 non-text file", app.status.get())
                    self.assertIn("asset.bin", {path.name for path in app.tree_paths.values()})
                    with (
                        patch.object(app.file_tree, "identify_row", return_value=item),
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    self.assertEqual(app.file_context_menu.index("end"), 1)
                    app.file_context_menu.invoke(1)
                    self.assertFalse(app.context_files)
                    self.assertEqual(app.file_tree.item("f:src/main.py", "text"), "main.py")
            finally:
                root.destroy()

    def test_selected_folders_share_add_and_remove_context_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            project = root_path / "project"
            first = project / "first"
            second = project / "second"
            first.mkdir(parents=True)
            second.mkdir()
            (first / "one.py").write_text("one", encoding="utf-8")
            (first / "two.txt").write_text("two", encoding="utf-8")
            (second / "three.md").write_text("three", encoding="utf-8")
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._load_project(project)
                    first_row = "d:first"
                    second_row = "d:second"
                    app.file_tree.selection_set(first_row, second_row)
                    event = SimpleNamespace(y=10, x_root=20, y_root=30)
                    with (
                        patch.object(app.file_tree, "identify_row", return_value=first_row),
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    self.assertEqual(app.file_context_menu.index("end"), 0)
                    app.file_context_menu.invoke(0)
                    self.assertEqual(len(app.context_files), 3)

                    app.file_tree.selection_set(first_row, second_row)
                    with (
                        patch.object(app.file_tree, "identify_row", return_value=first_row),
                        patch.object(app.file_context_menu, "tk_popup"),
                    ):
                        app._show_file_context_menu(event)
                    self.assertEqual(app.file_context_menu.index("end"), 1)
                    self.assertEqual(
                        app.file_context_menu.entrycget(1, "label"),
                        "Remove selected from context",
                    )
                    app.file_context_menu.invoke(1)
                    self.assertFalse(app.context_files)
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
                    self.assertEqual(
                        app.pasted_images_tree.item("context:image:1", "text"),
                        "* Clipboard image 1",
                    )
                    self.assertIn("Pasted images (1)", app.pasted_images_label.cget("text"))
                    self.assertEqual(len(app.pasted_image_thumbnails), 1)
                    self.assertIn("Added clipboard-1.png", app.status.get())
                    app.pasted_images_tree.selection_set("context:image:1")
                    app._remove_selected_context()
                    self.assertFalse(app.context_files)
                    self.assertFalse(app.pasted_images_frame.winfo_manager())
                    app._cleanup_clipboard_images()
                    self.assertIsNone(app.clipboard_image_directory)
            finally:
                root.destroy()

    def test_pasting_windows_clipboard_image_path_attaches_image_not_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            source_image = root_path / "ScreenClip" / "screen.png"
            source_image.parent.mkdir()
            Image.new("RGB", (4, 4), "blue").save(source_image)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch("src.app.ImageGrab.grabclipboard", return_value=[str(source_image)]),
                ):
                    app = DeepbridCodeApp(root)
                    result = app._paste_clipboard_image(SimpleNamespace())
                    prompt = build_prompt(
                        "Can you describe this image?",
                        list(app.context_files.values()),
                    )

                    self.assertEqual(result, "break")
                    self.assertEqual(len(app.context_files), 1)
                    self.assertIn("[Selected image: Clipboard image 1]", prompt)
                    self.assertNotIn(str(source_image), prompt)
                    self.assertNotIn("ScreenClip", prompt)
                    context_iid = app.context_tree_iids[
                        str(next(iter(app.context_files.values())).path)
                    ]
                    self.assertTrue(app.pasted_images_tree.exists(context_iid))
                    app.pasted_images_tree.selection_set(context_iid)
                    app._remove_selected_context()
                    self.assertEqual(len(app.context_files), 0)
                    self.assertFalse(app.pasted_images_tree.exists(context_iid))
                    app._cleanup_clipboard_images()
            finally:
                root.destroy()

    def test_pasting_clipboard_text_path_to_image_is_added_as_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            image_path = root_path / "screenshot.png"
            Image.new("RGB", (4, 4), "green").save(image_path)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch("src.app.ImageGrab.grabclipboard", return_value=None),
                    patch.object(root, "clipboard_get", return_value=str(image_path)),
                ):
                    app = DeepbridCodeApp(root)
                    self.assertEqual(app._paste_clipboard_image(SimpleNamespace()), "break")
                    self.assertEqual(len(app.context_files), 1)
                    app._cleanup_clipboard_images()
            finally:
                root.destroy()

    def test_plain_clipboard_text_uses_normal_paste_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                    patch("src.app.ImageGrab.grabclipboard", return_value=None),
                    patch.object(root, "clipboard_get", return_value="ordinary text"),
                ):
                    app = DeepbridCodeApp(root)
                    self.assertIsNone(app._paste_clipboard_image(SimpleNamespace()))
                    self.assertEqual(len(app.context_files), 0)
            finally:
                root.destroy()

    def test_each_prompt_has_a_timestamped_separator(self) -> None:
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
                    app._append_chat("You", "First prompt")
                    app._append_chat("Deepbrid AI", "First response")
                    app._append_chat("You", "Second prompt")
                    transcript = app.chat_output.get("1.0", "end")

                    self.assertEqual(
                        len(re.findall(r"-{20} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} -{20}", transcript)),
                        2,
                    )
                    self.assertLess(
                        transcript.index("First prompt"),
                        transcript.index("Second prompt"),
                    )
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
                        app.output_log_path,
                        app._set_output_logging,
                    )
                    dialog.dark_theme.set(True)
                    dialog._save_dark_theme()
                    dialog.wrap_text.set(False)
                    dialog._save_wrap_text()
                    self.assertFalse(hasattr(dialog, "output_log_enabled"))
                    log_path = root_path / "diagnostics.log"
                    dialog.output_log_path.set(str(log_path))
                    dialog._save_output_logging()
                    self.assertTrue(app.output_log_enabled)
                    self.assertEqual(app.settings.get(OUTPUT_LOG_PATH), str(log_path))
                    dialog._clear_output_log_path()

                self.assertTrue(app.dark_theme)
                self.assertTrue(app.settings.get_bool(DARK_THEME, default=False))
                self.assertFalse(app.settings.get_bool(WRAP_TEXT, default=True))
                self.assertFalse(app.wrap_text)
                self.assertFalse(app.output_log_enabled)
                self.assertEqual(app.settings.get(OUTPUT_LOG_PATH), "")
                self.assertEqual(dialog.status.get(), "Saved.")
                dialog.dialog.destroy()
            finally:
                root.destroy()

    def test_bottom_console_and_path_controlled_file_logging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root_path = Path(temporary_directory)
            log_path = root_path / "logs" / "deepbrid-code.log"
            root = tk.Tk()
            root.withdraw()
            try:
                with (
                    patch("src.app.SETTINGS_DATABASE", root_path / "settings.sqlite3"),
                    patch("src.app.APP_DATA_DIR", root_path),
                ):
                    app = DeepbridCodeApp(root)
                    app._set_output_logging(str(log_path))
                    app._log("A diagnostic message")
                    app._toggle_console()

                    self.assertTrue(log_path.is_file())
                    self.assertIn(str(app.console_panel), app.workspace.panes())
                    self.assertTrue(app.console_visible)
                    self.assertIn("A diagnostic message", log_path.read_text(encoding="utf-8"))
                    self.assertIn(
                        "A diagnostic message",
                        app.console_output.get("1.0", "end"),
                    )
                    self.assertEqual(app.settings.get(OUTPUT_LOG_PATH), str(log_path))
                    self.assertIn("A diagnostic message", app.console_history[-1])
                    app._toggle_console()
                    self.assertNotIn(str(app.console_panel), app.workspace.panes())
                    self.assertFalse(app.console_visible)
                    app._set_output_logging("")
                    app._log("Not written to file")
                    self.assertFalse(app.output_log_enabled)
                    self.assertEqual(app.settings.get(OUTPUT_LOG_PATH), "")
                    self.assertNotIn(
                        "Not written to file",
                        log_path.read_text(encoding="utf-8"),
                    )
            finally:
                root.destroy()

    def test_console_defaults_to_one_third_and_remembers_resized_height(self) -> None:
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
                    with (
                        patch.object(app.root, "after_idle") as after_idle,
                        patch.object(app.workspace, "winfo_height", return_value=900),
                        patch.object(app.workspace, "sashpos") as set_sash,
                    ):
                        app._toggle_console()
                        after_idle.assert_called_once()
                        app._restore_console_pane()
                        set_sash.assert_called_with(0, 600)

                    with (
                        patch.object(app.workspace, "winfo_height", return_value=900),
                        patch.object(app.workspace, "sashpos", return_value=500),
                    ):
                        app._toggle_console()
                    self.assertEqual(app.console_sash_position, 500)

                    with (
                        patch.object(app.root, "after_idle"),
                        patch.object(app.workspace, "winfo_height", return_value=900),
                        patch.object(app.workspace, "sashpos") as set_sash,
                    ):
                        app._toggle_console()
                        app._restore_console_pane()
                    set_sash.assert_called_with(0, 500)
            finally:
                root.destroy()

    def test_enter_sends_and_control_enter_inserts_newline(self) -> None:
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
                    with patch.object(app, "_send") as send:
                        self.assertEqual(app._send_on_return(SimpleNamespace()), "break")
                    send.assert_called_once_with()

                    app.message.insert("1.0", "first")
                    app.message.mark_set("insert", "end-1c")
                    self.assertEqual(
                        app._insert_message_newline(SimpleNamespace(widget=app.message)),
                        "break",
                    )
                    app.message.insert("insert", "second")
                    self.assertEqual(app.message.get("1.0", "end-1c"), "first\nsecond")
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
