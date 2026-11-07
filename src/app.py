from __future__ import annotations

import os
import queue
import sqlite3
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .browser import BrowserLaunchError, DeepbridChatBrowser
from .context import (
    ContextFile,
    build_prompt,
    context_kind,
    iter_project_files,
    read_text_context,
)
from .settings import AUTO_OPEN_CHROME, LAST_PROJECT, SettingsStore
from .settings_dialog import SettingsDialog

APP_DATA_DIR = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
) / "Deepbrid Code"
SETTINGS_DATABASE = APP_DATA_DIR / "settings.sqlite3"
MAX_IMAGE_PREVIEW_BYTES = 20 * 1024 * 1024


class DeepbridCodeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Deepbrid Code")
        self.root.geometry("1100x720")
        self.settings = SettingsStore(SETTINGS_DATABASE)
        self.auto_open_chrome = self.settings.get_bool(AUTO_OPEN_CHROME, default=True)
        self.last_project = self.settings.get(LAST_PROJECT)
        self.project_root: Path | None = None
        self.tree_paths: dict[str, Path] = {}
        self.context_files: dict[str, ContextFile] = {}
        self.context_order: list[str] = []
        self.preview_image: tk.PhotoImage | None = None
        self.chat_browser = DeepbridChatBrowser(APP_DATA_DIR / "chrome-profile")
        self.chat_events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.chat_request_active = False
        self.browser_request_active = False

        self._build_ui()
        self.root.after(200, self._poll_chat_events)
        self.root.after(100, self._startup)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open folder...", command=self._open_folder).pack(side="left")
        ttk.Button(toolbar, text="Open Deepbrid AI Chat", command=self._open_browser).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(toolbar, text="Settings", command=self._open_settings).pack(
            side="left",
            padx=(8, 0),
        )
        self.project_label = ttk.Label(toolbar, text="No project open")
        self.project_label.pack(side="left", padx=12)

        main = ttk.Panedwindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        files_panel = ttk.Frame(main, padding=4)
        preview_panel = ttk.Frame(main, padding=4)
        context_panel = ttk.Frame(main, padding=4)
        main.add(files_panel, weight=1)
        main.add(preview_panel, weight=2)
        main.add(context_panel, weight=2)

        ttk.Label(files_panel, text="Project files").pack(anchor="w", pady=(0, 4))
        self.file_tree = ttk.Treeview(files_panel, show="tree", selectmode="extended")
        self.file_tree.pack(fill="both", expand=True)
        self.file_tree.bind("<<TreeviewSelect>>", self._preview_selection)
        ttk.Button(files_panel, text="Add selected to context", command=self._add_context).pack(
            fill="x", pady=(6, 0)
        )

        ttk.Label(preview_panel, text="Preview").pack(anchor="w", pady=(0, 4))
        self.preview = tk.Text(preview_panel, wrap="none", state="disabled")
        self.preview.pack(fill="both", expand=True)
        self.preview_image_label = ttk.Label(preview_panel)
        self.preview_image_label.pack(fill="x")

        ttk.Label(context_panel, text="Included context (nothing is sent automatically)").pack(
            anchor="w", pady=(0, 4)
        )
        self.context_list = tk.Listbox(context_panel, height=8, selectmode="extended")
        self.context_list.pack(fill="x")
        ttk.Button(context_panel, text="Remove selected context", command=self._remove_context).pack(
            fill="x", pady=(4, 8)
        )

        ttk.Label(context_panel, text="Conversation (kept in memory only)").pack(anchor="w")
        self.chat_output = tk.Text(context_panel, height=10, wrap="word", state="disabled")
        self.chat_output.pack(fill="both", expand=True, pady=(4, 8))

        ttk.Label(context_panel, text="Message").pack(anchor="w")
        self.message = tk.Text(context_panel, height=5, wrap="word")
        self.message.pack(fill="both", expand=True, pady=(4, 6))
        actions = ttk.Frame(context_panel)
        actions.pack(fill="x")
        ttk.Button(actions, text="Copy prompt for Deepbrid AI Chat", command=self._copy_prompt).pack(
            fill="x"
        )
        ttk.Button(actions, text="Send to Deepbrid AI Chat", command=self._send).pack(
            fill="x", pady=(4, 0)
        )

        self.status = tk.StringVar(
            value="Selected context stays local until sent to Deepbrid AI Chat."
        )
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w", padding=5).pack(
            fill="x", side="bottom"
        )
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", side="bottom")

    def _open_folder(self) -> None:
        selected = filedialog.askdirectory(title="Open project folder")
        if not selected:
            return
        self._load_project(Path(selected))

    def _load_project(self, root: Path) -> None:
        if not root.is_dir():
            messagebox.showerror("Could not open folder", f"{root} is not a folder.")
            return
        try:
            entries = list(iter_project_files(root))
        except OSError as error:
            messagebox.showerror("Could not open folder", str(error))
            return
        self.project_root = root
        self.context_files.clear()
        self.context_order.clear()
        self.context_list.delete(0, "end")
        children = self.file_tree.get_children()
        if children:
            self.file_tree.delete(*children)
        self.tree_paths.clear()
        self.preview_image = None
        self.preview_image_label.configure(image="", text="")
        directory_nodes: dict[Path, str] = {root: ""}
        for path in entries:
            parent = path.parent
            missing: list[Path] = []
            while parent not in directory_nodes and parent != root:
                missing.append(parent)
                parent = parent.parent
            parent_iid = directory_nodes.get(parent, "")
            for directory in reversed(missing):
                iid = f"d:{directory.relative_to(root).as_posix()}"
                self.file_tree.insert(parent_iid, "end", iid=iid, text=directory.name, open=False)
                directory_nodes[directory] = iid
                parent_iid = iid
            iid = f"f:{path.relative_to(root).as_posix()}"
            self.file_tree.insert(parent_iid, "end", iid=iid, text=path.name)
            self.tree_paths[iid] = path
        self.project_label.configure(text=str(root))
        self._set_preview("")
        self.project_root = root.resolve()
        try:
            self.settings.set(LAST_PROJECT, str(self.project_root))
        except (OSError, sqlite3.Error) as error:
            self.status.set(
                f"Opened {root}, but could not save the last project setting: {error}"
            )
            return
        self.status.set(f"Opened {root}. Select files explicitly to add context.")

    def _startup(self) -> None:
        if self.last_project:
            project = Path(self.last_project)
            if project.is_dir():
                self._load_project(project)
            else:
                self.status.set(
                    f"The previously opened project is unavailable: {project}"
                )
        if self.auto_open_chrome:
            self._start_browser_open(startup=True)

    def _open_settings(self) -> None:
        try:
            SettingsDialog(
                self.root,
                self.settings,
                self.auto_open_chrome,
                self._set_auto_open_chrome,
            )
        except (OSError, sqlite3.Error) as error:
            self.status.set(f"Could not open Settings: {error}")

    def _set_auto_open_chrome(self, enabled: bool) -> None:
        self.auto_open_chrome = enabled

    def _preview_selection(self, _event: tk.Event) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return
        path = self.tree_paths.get(selection[0])
        if path is None:
            return
        kind = context_kind(path)
        if kind == "text":
            try:
                self.preview_image = None
                self.preview_image_label.configure(image="", text="")
                self._set_preview(read_text_context(path))
            except (OSError, ValueError) as error:
                self._set_preview(str(error))
        elif kind == "image":
            try:
                size = path.stat().st_size
                self._set_preview(f"Image: {path.name}\nSize: {size:,} bytes")
                if size > MAX_IMAGE_PREVIEW_BYTES:
                    raise ValueError(
                        f"Image exceeds the {MAX_IMAGE_PREVIEW_BYTES // (1024 * 1024)} MiB preview limit."
                    )
                self.preview_image = tk.PhotoImage(file=str(path))
                self.preview_image_label.configure(image=self.preview_image, text="")
            except (OSError, ValueError, tk.TclError) as error:
                self.preview_image = None
                self.preview_image_label.configure(
                    image="",
                    text=f"Preview unavailable ({error}); the image can still be selected.",
                )
        else:
            self.preview_image = None
            self.preview_image_label.configure(image="", text="")
            self._set_preview(f"{path.name} is not a supported text or image context file.")

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _add_context(self) -> None:
        if self.project_root is None:
            self.status.set("Open a project folder first.")
            return
        selected_items = self.file_tree.selection()
        if not selected_items:
            self.status.set("Select one or more supported files to add context.")
            return
        skipped: list[str] = []
        for iid in selected_items:
            path = self.tree_paths.get(iid)
            if path is None:
                continue
            kind = context_kind(path)
            if kind is None:
                skipped.append(path.name)
                continue
            key = str(path)
            if key not in self.context_files:
                self.context_files[key] = ContextFile(path, kind)
                self.context_order.append(key)
                self.context_list.insert("end", f"{path.relative_to(self.project_root)} ({kind})")
        if skipped:
            self.status.set(
                f"Skipped unsupported file(s): {', '.join(skipped)}. "
                f"{len(self.context_files)} context item(s) selected."
            )
        else:
            self.status.set(
                f"{len(self.context_files)} context item(s) selected."
            )

    def _remove_context(self) -> None:
        selected = list(self.context_list.curselection())
        for index in reversed(selected):
            key = self.context_order.pop(index)
            self.context_files.pop(key, None)
            self.context_list.delete(index)
        self.status.set(f"{len(self.context_files)} context item(s) selected.")

    def _copy_prompt(self) -> None:
        try:
            prompt = build_prompt(
                self.message.get("1.0", "end-1c"),
                list(self.context_files.values()),
                self.project_root,
            )
        except (OSError, ValueError) as error:
            self.status.set(f"Could not prepare prompt: {error}")
            return
        if not prompt:
            self.status.set("Add a message or context before copying.")
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(prompt)
        except tk.TclError as error:
            self.status.set(f"Could not copy prompt to the clipboard: {error}")
            return
        self.status.set(
            "Prompt copied to clipboard. Paste it yourself in Deepbrid AI Chat; "
            "attach the selected images there manually."
        )

    def _send(self) -> None:
        if self.chat_request_active:
            self.status.set("Wait for the current Deepbrid AI Chat response to finish.")
            return
        if self.browser_request_active:
            self.status.set("Wait for the dedicated Chrome profile to finish opening.")
            return
        try:
            prompt = build_prompt(
                self.message.get("1.0", "end-1c"),
                list(self.context_files.values()),
                self.project_root,
            )
        except (OSError, ValueError) as error:
            self.status.set(f"Could not prepare prompt: {error}")
            return
        if not prompt:
            self.status.set("Add a message or context before sending.")
            return

        image_paths = [
            item.path for item in self.context_files.values() if item.kind == "image"
        ]
        self.chat_request_active = True
        self._append_chat("You", prompt)
        if image_paths:
            self._append_chat("Images attached", "\n".join(path.name for path in image_paths))
        self.message.delete("1.0", "end")
        self.status.set("Sending message to Deepbrid AI Chat. Waiting for its response...")
        self.progress.start(12)
        worker = threading.Thread(
            target=self._chat_worker,
            args=(prompt, image_paths, self.project_root),
            name="deepbrid-chat-ui",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self.chat_request_active = False
            self.progress.stop()
            self.status.set(f"Could not start the chat request: {error}")

    def _chat_worker(
        self,
        prompt: str,
        image_paths: list[Path],
        project_root: Path | None,
    ) -> None:
        try:
            response = self.chat_browser.send_message(prompt, image_paths, project_root)
        except BrowserLaunchError as error:
            self.chat_events.put(("chat-error", str(error)))
        except (OSError, ValueError, RuntimeError) as error:
            self.chat_events.put(("chat-error", f"Chat operation failed: {error}"))
        else:
            self.chat_events.put(("chat-success", response))

    def _poll_chat_events(self) -> None:
        while True:
            try:
                event, content = self.chat_events.get_nowait()
            except queue.Empty:
                break
            if event.startswith("chat-"):
                self.chat_request_active = False
                self.progress.stop()
            elif event.startswith("browser-"):
                self.browser_request_active = False
                self.progress.stop()
            if event == "chat-success":
                self._append_chat("Deepbrid AI", content)
                self.status.set(f"Deepbrid AI Chat replied ({len(content)} characters).")
            elif event == "chat-error":
                self._append_chat("Deepbrid AI Chat status", content)
                self.status.set(content)
            elif event == "browser-chat":
                self.status.set("Deepbrid AI Chat is open and ready.")
            elif event == "browser-login":
                self.status.set("Chrome is open to Deepbrid login. Sign in, then send your message.")
            elif event == "browser-error":
                self.status.set(content)
        self.root.after(200, self._poll_chat_events)

    def _append_chat(self, speaker: str, content: str) -> None:
        self.chat_output.configure(state="normal")
        self.chat_output.insert("end", f"{speaker}:\n{content}\n\n")
        self.chat_output.see("end")
        self.chat_output.configure(state="disabled")

    def _open_browser(self) -> None:
        self._start_browser_open(startup=False)

    def _start_browser_open(self, startup: bool) -> None:
        if self.browser_request_active:
            return
        if self.chat_request_active:
            self.status.set("Wait for the current Deepbrid AI Chat request to finish.")
            return
        self.browser_request_active = True
        self.status.set(
            "Opening Deepbrid AI Chat..." if not startup else "Opening Chrome on startup..."
        )
        self.progress.start(12)
        worker = threading.Thread(
            target=self._browser_worker,
            name="deepbrid-chat-browser",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self.browser_request_active = False
            self.progress.stop()
            self.status.set(f"Could not start Chrome: {error}")

    def _browser_worker(self) -> None:
        try:
            landing_page = self.chat_browser.open_for_chat()
        except (BrowserLaunchError, OSError, RuntimeError) as error:
            self.chat_events.put(("browser-error", f"Could not open Deepbrid AI Chat: {error}"))
        else:
            self.chat_events.put((f"browser-{landing_page}", ""))


def main() -> None:
    root = tk.Tk()
    try:
        DeepbridCodeApp(root)
    except (OSError, sqlite3.Error, ValueError) as error:
        messagebox.showerror("Could not start Deepbrid Code", str(error))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
