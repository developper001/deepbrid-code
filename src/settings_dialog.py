from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Protocol

from .settings import (
    AUTO_OPEN_CHROME,
    DARK_THEME,
    REMOVE_IMAGES_AFTER_SEND,
    WRAP_TEXT,
)


class SettingsBackend(Protocol):
    def set_bool(self, name: str, value: bool) -> None: ...


class SettingsDialog:
    def __init__(
        self,
        parent: tk.Tk,
        settings: SettingsBackend,
        auto_open_chrome: bool,
        on_auto_open_changed: Callable[[bool], None],
        dark_theme: bool,
        on_dark_theme_changed: Callable[[bool], None],
        wrap_text: bool,
        on_wrap_text_changed: Callable[[bool], None],
        remove_images_after_send: bool,
        on_remove_images_after_send_changed: Callable[[bool], None],
        output_log_path: str,
        on_output_logging_changed: Callable[[str], None],
    ) -> None:
        self.settings = settings
        self.on_auto_open_changed = on_auto_open_changed
        self.on_dark_theme_changed = on_dark_theme_changed
        self.on_wrap_text_changed = on_wrap_text_changed
        self.on_remove_images_after_send_changed = on_remove_images_after_send_changed
        self.on_output_logging_changed = on_output_logging_changed
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("640x520")
        self.dialog.minsize(560, 460)
        self.dialog.transient(parent)

        frame = ttk.Frame(self.dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(0, weight=1)

        navigation = ttk.Frame(frame, padding=(0, 0, 16, 0))
        navigation.grid(row=0, column=0, sticky="ns")
        ttk.Label(navigation, text="Sections").pack(anchor="w", pady=(0, 8))
        ttk.Label(
            navigation,
            text="Startup",
            relief="solid",
            padding=(10, 6),
        ).pack(fill="x")
        ttk.Label(
            navigation,
            text="Appearance",
            relief="solid",
            padding=(10, 6),
        ).pack(fill="x", pady=(6, 0))
        ttk.Label(
            navigation,
            text="Diagnostics",
            relief="solid",
            padding=(10, 6),
        ).pack(fill="x", pady=(6, 0))

        content = ttk.Frame(frame, padding=12, relief="groove")
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        ttk.Label(content, text="Startup", font=("TkDefaultFont", 14, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
            pady=(0, 12),
        )
        self.status = tk.StringVar(master=self.dialog)
        self.enabled = tk.BooleanVar(master=self.dialog, value=auto_open_chrome)
        ttk.Checkbutton(
            content,
            text="Open Deepbrid AI Chat in Chrome when Deepbrid Code starts",
            variable=self.enabled,
            command=self._save,
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            content,
            text=(
                "Uses the app's separate Chrome profile. If you have not signed in, "
                "Deepbrid will show its login page. You can still open the chat manually "
                "from the app."
            ),
            wraplength=420,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Separator(content).grid(row=3, column=0, sticky="ew", pady=(16, 12))
        ttk.Label(content, text="Appearance", font=("TkDefaultFont", 12, "bold")).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(0, 8),
        )
        self.dark_theme = tk.BooleanVar(master=self.dialog, value=dark_theme)
        self.wrap_text = tk.BooleanVar(master=self.dialog, value=wrap_text)
        ttk.Checkbutton(
            content,
            text="Use dark mode",
            variable=self.dark_theme,
            command=self._save_dark_theme,
        ).grid(row=5, column=0, sticky="w")
        ttk.Checkbutton(
            content,
            text="Wrap text in file preview",
            variable=self.wrap_text,
            command=self._save_wrap_text,
        ).grid(row=6, column=0, sticky="w", pady=(6, 0))
        self.remove_images_after_send = tk.BooleanVar(
            master=self.dialog,
            value=remove_images_after_send,
        )
        ttk.Checkbutton(
            content,
            text="Remove images from context after sending",
            variable=self.remove_images_after_send,
            command=self._save_remove_images_after_send,
        ).grid(row=7, column=0, sticky="w", pady=(6, 0))
        ttk.Separator(content).grid(row=8, column=0, sticky="ew", pady=(14, 10))
        ttk.Label(content, text="Diagnostics", font=("TkDefaultFont", 12, "bold")).grid(
            row=9,
            column=0,
            sticky="w",
            pady=(0, 6),
        )
        self.output_log_path = tk.StringVar(
            master=self.dialog,
            value=output_log_path,
        )
        self.output_log_status = tk.StringVar(master=self.dialog)
        self.output_log_status.set(
            "Console output is appended to this file."
            if output_log_path
            else "File logging is disabled."
        )
        ttk.Label(content, text="Log file path (empty disables file logging)").grid(
            row=10,
            column=0,
            sticky="w",
        )
        log_path_controls = ttk.Frame(content)
        log_path_controls.grid(row=11, column=0, sticky="ew", pady=(6, 0))
        log_path_controls.columnconfigure(0, weight=1)
        ttk.Entry(
            log_path_controls,
            textvariable=self.output_log_path,
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            log_path_controls,
            text="Browse...",
            command=self._browse_output_log,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(
            log_path_controls,
            text="Save",
            command=self._save_output_logging,
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(
            log_path_controls,
            text="Clear",
            command=self._clear_output_log_path,
        ).grid(row=0, column=3, padx=(8, 0))
        ttk.Label(content, textvariable=self.output_log_status).grid(
            row=12,
            column=0,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Label(content, textvariable=self.status).grid(
            row=13,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Button(frame, text="Close", command=self.dialog.destroy).grid(
            row=1,
            column=1,
            sticky="e",
            pady=(12, 0),
        )
        self.dialog.grab_set()
        self.saved_enabled = auto_open_chrome
        self.saved_dark_theme = dark_theme
        self.saved_wrap_text = wrap_text
        self.saved_remove_images_after_send = remove_images_after_send
        self.saved_output_log_path = output_log_path

    def _save(self) -> None:
        enabled = self.enabled.get()
        try:
            self.settings.set_bool(AUTO_OPEN_CHROME, enabled)
        except (OSError, sqlite3.Error) as error:
            self.enabled.set(self.saved_enabled)
            self.status.set(f"Could not save setting: {error}")
            return
        self.saved_enabled = enabled
        self.on_auto_open_changed(enabled)
        self.status.set("Saved.")

    def _save_dark_theme(self) -> None:
        enabled = self.dark_theme.get()
        try:
            self.settings.set_bool(DARK_THEME, enabled)
        except (OSError, sqlite3.Error) as error:
            self.dark_theme.set(self.saved_dark_theme)
            self.status.set(f"Could not save setting: {error}")
            return
        self.saved_dark_theme = enabled
        self.on_dark_theme_changed(enabled)
        self.dialog.configure(
            background="#202522" if enabled else "#f0f2f0",
        )
        self.status.set("Saved.")

    def _save_wrap_text(self) -> None:
        enabled = self.wrap_text.get()
        try:
            self.settings.set_bool(WRAP_TEXT, enabled)
        except (OSError, sqlite3.Error) as error:
            self.wrap_text.set(self.saved_wrap_text)
            self.status.set(f"Could not save setting: {error}")
            return
        self.saved_wrap_text = enabled
        self.on_wrap_text_changed(enabled)
        self.status.set("Saved.")

    def _save_remove_images_after_send(self) -> None:
        enabled = self.remove_images_after_send.get()
        try:
            self.settings.set_bool(REMOVE_IMAGES_AFTER_SEND, enabled)
        except (OSError, sqlite3.Error) as error:
            self.remove_images_after_send.set(self.saved_remove_images_after_send)
            self.status.set(f"Could not save setting: {error}")
            return
        self.saved_remove_images_after_send = enabled
        self.on_remove_images_after_send_changed(enabled)
        self.status.set("Saved.")

    def _save_output_logging(self) -> None:
        path = self.output_log_path.get()
        try:
            self.on_output_logging_changed(path)
        except (OSError, ValueError, sqlite3.Error) as error:
            self.output_log_path.set(self.saved_output_log_path)
            self.output_log_status.set(f"Could not save output log setting: {error}")
            return
        self.saved_output_log_path = path
        self.output_log_status.set(
            "Console output is appended to the selected file."
            if path.strip()
            else "File logging is disabled."
        )

    def _browse_output_log(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.dialog,
            title="Choose console log file",
            initialfile=self.output_log_path.get() or "deepbrid-code.log",
            defaultextension=".log",
            filetypes=(("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*")),
        )
        if not selected:
            return
        self.output_log_path.set(selected)
        self._save_output_logging()

    def _clear_output_log_path(self) -> None:
        self.output_log_path.set("")
        self._save_output_logging()
