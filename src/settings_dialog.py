from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable, Protocol

from .settings import AUTO_OPEN_CHROME, DARK_THEME, WRAP_TEXT


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
        output_log_enabled: bool,
        output_log_path: str,
        on_output_logging_changed: Callable[[bool, str], None],
    ) -> None:
        self.settings = settings
        self.on_auto_open_changed = on_auto_open_changed
        self.on_dark_theme_changed = on_dark_theme_changed
        self.on_wrap_text_changed = on_wrap_text_changed
        self.on_output_logging_changed = on_output_logging_changed
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("640x480")
        self.dialog.minsize(560, 420)
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
        ttk.Separator(content).grid(row=7, column=0, sticky="ew", pady=(14, 10))
        ttk.Label(content, text="Diagnostics", font=("TkDefaultFont", 12, "bold")).grid(
            row=8,
            column=0,
            sticky="w",
            pady=(0, 6),
        )
        self.output_log_enabled = tk.BooleanVar(
            master=self.dialog,
            value=output_log_enabled,
        )
        self.output_log_path = tk.StringVar(
            master=self.dialog,
            value=output_log_path,
        )
        self.output_log_status = tk.StringVar(master=self.dialog)
        ttk.Checkbutton(
            content,
            text="Append console logs to a file",
            variable=self.output_log_enabled,
            command=self._save_output_logging,
        ).grid(row=9, column=0, sticky="w")
        log_path_controls = ttk.Frame(content)
        log_path_controls.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        log_path_controls.columnconfigure(0, weight=1)
        ttk.Entry(
            log_path_controls,
            textvariable=self.output_log_path,
            state="readonly",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            log_path_controls,
            text="Browse...",
            command=self._browse_output_log,
        ).grid(row=0, column=1, padx=(8, 0))
        ttk.Label(content, textvariable=self.output_log_status).grid(
            row=11,
            column=0,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Label(content, textvariable=self.status).grid(
            row=12,
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
        self.saved_output_log_enabled = output_log_enabled
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

    def _save_output_logging(self) -> None:
        enabled = self.output_log_enabled.get()
        path = self.output_log_path.get()
        try:
            self.on_output_logging_changed(enabled, path)
        except (OSError, ValueError, sqlite3.Error) as error:
            self.output_log_enabled.set(self.saved_output_log_enabled)
            self.output_log_path.set(self.saved_output_log_path)
            self.output_log_status.set(f"Could not save output log setting: {error}")
            return
        self.saved_output_log_enabled = enabled
        self.saved_output_log_path = path
        self.output_log_status.set(
            "Console output is appended to the selected file."
            if enabled
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
