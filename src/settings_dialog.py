from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk
from typing import Callable, Protocol

from .settings import AUTO_OPEN_CHROME


class SettingsBackend(Protocol):
    def set_bool(self, name: str, value: bool) -> None: ...


class SettingsDialog:
    def __init__(
        self,
        parent: tk.Tk,
        settings: SettingsBackend,
        auto_open_chrome: bool,
        on_auto_open_changed: Callable[[bool], None],
    ) -> None:
        self.settings = settings
        self.on_auto_open_changed = on_auto_open_changed
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("640x400")
        self.dialog.minsize(560, 340)
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
        ttk.Label(content, textvariable=self.status).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Button(frame, text="Close", command=self.dialog.destroy).grid(
            row=1,
            column=1,
            sticky="e",
            pady=(12, 0),
        )
        self.dialog.grab_set()
        self.saved_enabled = auto_open_chrome

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
