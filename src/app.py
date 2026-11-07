from __future__ import annotations

import os
import queue
import sqlite3
import tempfile
import threading
import tkinter as tk
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from types import TracebackType

from PIL import Image, ImageGrab, ImageTk

from .browser import BrowserLaunchError, ChatSession, DeepbridChatBrowser
from .context import (
    ContextFile,
    build_prompt,
    context_kind,
    iter_project_files,
    read_text_context,
    UPLOAD_FILE_EXTENSIONS,
    UPLOAD_IMAGE_EXTENSIONS,
    upload_context_kind,
)
from .logo import create_brand_icon
from .settings import (
    AUTO_OPEN_CHROME,
    DARK_THEME,
    DIAGNOSTICS_ENABLED,
    LAST_PROJECT,
    OUTPUT_LOG_PATH,
    REMOVE_IMAGES_AFTER_SEND,
    WRAP_TEXT,
    SettingsStore,
)
from .settings_dialog import SettingsDialog

APP_DATA_DIR = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
) / "Deepbrid Code"
SETTINGS_DATABASE = APP_DATA_DIR / "settings.sqlite3"
APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_LOG_PATH = APP_ROOT / "diagnostics" / "deepbrid-code.log"
MAX_IMAGE_PREVIEW_BYTES = 20 * 1024 * 1024
APP_ICON_PATH = Path(__file__).parent / "assets" / "deepbrid-code.ico"
AI_MODELS = (
    "GPT-6.1 Sol · Best",
    "GPT-6 Luna · Fast",
    "Grok 4.7",
    "Gemini 3.8 Flash · Fast",
    "Gemini 4 Argon",
)
AI_MODES = (
    "Code Assistant",
    "Document Analyst",
    "Writing Partner",
    "Patient Tutor",
    "Summarizer",
    "Brainstormer",
    "Email Helper",
)


class DeepbridCodeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Deepbrid Code")
        self.root.geometry("1180x760")
        self.root.minsize(900, 600)
        self.settings = SettingsStore(SETTINGS_DATABASE)
        self.auto_open_chrome = self.settings.get_bool(AUTO_OPEN_CHROME, default=True)
        self.dark_theme = self.settings.get_bool(DARK_THEME, default=False)
        self.wrap_text = self.settings.get_bool(WRAP_TEXT, default=True)
        self.remove_images_after_send = self.settings.get_bool(
            REMOVE_IMAGES_AFTER_SEND,
            default=True,
        )
        saved_log_path = self.settings.get(OUTPUT_LOG_PATH)
        self.output_log_path = (
            str(DEFAULT_OUTPUT_LOG_PATH)
            if saved_log_path is None
            else saved_log_path
        )
        self.diagnostics_enabled = self.settings.get_bool(
            DIAGNOSTICS_ENABLED,
            default=False,
        )
        self.output_log_enabled = (
            self.diagnostics_enabled and bool(self.output_log_path.strip())
        )
        self.last_project = self.settings.get(LAST_PROJECT)
        self.project_root: Path | None = None
        self.tree_paths: dict[str, Path] = {}
        self.tree_directories: dict[str, Path] = {}
        self.context_files: dict[str, ContextFile] = {}
        self.context_order: list[str] = []
        self.context_tree_iids: dict[str, str] = {}
        self.external_context_tree_items: dict[str, ContextFile] = {}
        self.next_external_tree_id = 1
        self.additional_file_thumbnails: dict[str, ImageTk.PhotoImage] = {}
        self.preview_image: tk.PhotoImage | None = None
        self.preview_path: Path | None = None
        self.window_icons: tuple[tk.PhotoImage, ...] = ()
        self.clipboard_image_directory: tempfile.TemporaryDirectory[str] | None = None
        self.clipboard_images: set[Path] = set()
        self.cleanup_clipboard_after_chat = False
        self.pending_image_context_keys: list[str] = []
        self.pending_remove_images_after_send = True
        self.chat_browser = DeepbridChatBrowser(APP_DATA_DIR / "chrome-profile")
        self.chat_events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.sessions_events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.sessions_window: tk.Toplevel | None = None
        self.sessions_tree: ttk.Treeview | None = None
        self.sessions_status: tk.StringVar | None = None
        self.sessions_filter = tk.StringVar(master=self.root)
        self.sessions: list[ChatSession] = []
        self.session_rows: dict[str, ChatSession] = {}
        self.sessions_request_active = False
        self.ai_model = AI_MODELS[0]
        self.ai_mode = AI_MODES[0]
        self.web_enabled = False
        self.console_events: queue.Queue[str] = queue.Queue()
        self.console_history: deque[str] = deque(maxlen=2000)
        self.console_output: tk.Text | None = None
        self.console_visible = False
        self.console_sash_position: int | None = None
        self._log_lock = threading.Lock()
        self._previous_callback_exception = self.root.report_callback_exception
        self._poll_after_id: str | None = None
        self._startup_after_id: str | None = None
        self._initial_sash_set = False
        self.chat_request_active = False
        self.browser_request_active = False

        self._build_ui()
        self._apply_theme()
        self.root.report_callback_exception = self._report_callback_exception
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        if self.output_log_enabled:
            try:
                self._validate_output_log_path(self.output_log_path)
            except (OSError, ValueError) as error:
                self.output_log_enabled = False
                self.status.set(f"Could not enable diagnostics file logging: {error}")
                self._log(f"Could not enable diagnostics file logging: {error}")
        self._log("Deepbrid Code started.")
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._poll_after_id = self.root.after(200, self._poll_chat_events)
        self._startup_after_id = self.root.after(100, self._startup)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        self.logo_image = create_brand_icon(self.root, self.dark_theme, 48)
        self._set_window_icons()
        self.logo_label = ttk.Label(toolbar, image=self.logo_image)
        self.logo_label.pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Open folder...", command=self._open_folder).pack(side="left")
        ttk.Button(toolbar, text="Open Deepbrid AI Chat", command=self._open_browser).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(toolbar, text="Settings", command=self._open_settings).pack(
            side="left",
            padx=(8, 0),
        )
        self.sessions_button = ttk.Button(toolbar, text="Sessions", command=self._open_sessions)
        self.sessions_button.pack(
            side="left",
            padx=(8, 0),
        )
        ttk.Label(toolbar, text="Mode").pack(side="left", padx=(16, 4))
        self.mode_selector = ttk.Combobox(
            toolbar,
            state="readonly",
            values=AI_MODES,
            width=20,
        )
        self.mode_selector.set(self.ai_mode)
        self.mode_selector.pack(side="left")
        self.mode_selector.bind("<<ComboboxSelected>>", self._mode_changed)

        self.workspace = ttk.Panedwindow(self.root, orient="vertical")
        self.workspace.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        main = ttk.Panedwindow(self.workspace, orient="horizontal")
        self.main_pane = main
        self.workspace.add(main, weight=4)

        files_panel = ttk.Frame(main, padding=4)
        chat_panel = ttk.Frame(main, padding=4)
        main.add(files_panel, weight=1)
        main.add(chat_panel, weight=3)
        main.bind("<Configure>", self._size_initial_panes, add="+")
        main.bind("<Configure>", self._size_project_tree, add="+")

        files_panel.rowconfigure(1, weight=0, minsize=220)
        files_panel.columnconfigure(0, weight=1)
        ttk.Label(
            files_panel,
            text="Project files (* = included in context)",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.file_tree = ttk.Treeview(
            files_panel,
            show="tree",
            selectmode="extended",
            height=10,
        )
        self.file_tree.grid(row=1, column=0, sticky="nsew")
        self.file_tree.bind("<<TreeviewSelect>>", self._preview_selection)
        self.file_tree.bind("<Button-3>", self._show_file_context_menu)
        self.file_context_menu = tk.Menu(self.root, tearoff=False)
        self.additional_files_frame = ttk.Frame(files_panel)
        self.additional_files_frame.columnconfigure(0, weight=1)
        self.additional_files_label = ttk.Label(self.additional_files_frame, text="Additional files (0)")
        self.additional_files_label.grid(row=0, column=0, sticky="w", pady=(2, 2))
        self.additional_files_tree = ttk.Treeview(
            self.additional_files_frame,
            style="AdditionalFiles.Treeview",
            show="tree",
            height=3,
            selectmode="extended",
        )
        additional_files_scrollbar = ttk.Scrollbar(
            self.additional_files_frame,
            orient="vertical",
            command=self.additional_files_tree.yview,
        )
        self.additional_files_tree.configure(yscrollcommand=additional_files_scrollbar.set)
        self.additional_files_tree.grid(row=1, column=0, sticky="ew")
        additional_files_scrollbar.grid(row=1, column=1, sticky="ns")
        self.additional_files_tree.bind("<Button-3>", self._show_additional_file_menu)
        self.additional_files_tree.bind("<Configure>", self._refresh_additional_file_labels)
        self.additional_file_menu = tk.Menu(self.root, tearoff=False)
        self.additional_file_menu.add_command(
            label="Remove from context",
            command=self._remove_selected_context,
        )
        self.additional_files_frame.grid(row=2, column=0, sticky="ew")
        self.additional_files_frame.grid_remove()
        ttk.Label(files_panel, text="Preview").grid(
            row=3,
            column=0,
            sticky="w",
            pady=(0, 4),
        )
        preview_frame = ttk.Frame(files_panel)
        preview_frame.grid(row=4, column=0, sticky="nsew")
        files_panel.rowconfigure(4, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.preview = tk.Text(
            preview_frame,
            wrap="word" if self.wrap_text else "none",
            state="disabled",
            xscrollcommand=lambda first, last: self.preview_xscroll.set(first, last),
            yscrollcommand=lambda first, last: self.preview_yscroll.set(first, last),
        )
        self.preview_yscroll = ttk.Scrollbar(
            preview_frame,
            orient="vertical",
            command=self.preview.yview,
        )
        self.preview_xscroll = ttk.Scrollbar(
            preview_frame,
            orient="horizontal",
            command=self.preview.xview,
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview_yscroll.grid(row=0, column=1, sticky="ns")
        self.preview_xscroll.grid(row=1, column=0, sticky="ew")
        self.preview_image_label = ttk.Label(files_panel)
        self.preview_image_label.grid(row=5, column=0, sticky="ew")

        ttk.Label(chat_panel, text="Conversation (kept in memory only)").pack(anchor="w")
        self.chat_output = tk.Text(chat_panel, height=20, wrap="word", state="disabled")
        self.chat_output.pack(fill="both", expand=True, pady=(4, 8))

        ttk.Label(chat_panel, text="Message").pack(anchor="w")
        self.message = tk.Text(chat_panel, height=7, wrap="word")
        self.message.pack(fill="x", pady=(4, 6))
        self.message.bind("<Control-v>", self._paste_clipboard_image)
        self.message.bind("<Control-V>", self._paste_clipboard_image)
        self.message.bind("<Shift-Insert>", self._paste_clipboard_image)
        self.message.bind("<Return>", self._send_on_return)
        self.message.bind("<Control-Return>", self._insert_message_newline)
        actions = ttk.Frame(chat_panel)
        actions.pack(fill="x")
        self.console_toggle_button = ttk.Button(
            actions,
            text="Toggle Console",
            command=self._toggle_console,
        )
        self.console_toggle_button.pack(side="left", pady=(4, 0))
        self.add_files_button = ttk.Button(
            actions,
            text="Add files...",
            command=self._add_additional_files,
        )
        self.add_files_button.pack(side="left", padx=(8, 0), pady=(4, 0))
        self.model_selector = ttk.Combobox(
            actions,
            state="readonly",
            values=AI_MODELS,
            width=22,
        )
        self.model_selector.set(self.ai_model)
        self.model_selector.pack(side="left", padx=(12, 0), pady=(4, 0))
        self.model_selector.bind("<<ComboboxSelected>>", self._model_changed)
        self.web_var = tk.BooleanVar(master=self.root, value=False)
        self.web_button = ttk.Checkbutton(
            actions,
            text="Web",
            variable=self.web_var,
            command=self._web_changed,
            style="Toolbutton",
        )
        self.web_button.pack(side="left", padx=(8, 0), pady=(4, 0))
        self.send_button = ttk.Button(actions, text="Send", command=self._send)
        self.send_button.pack(
            side="right",
            pady=(4, 0),
        )

        self.status = tk.StringVar(
            value="Selected context stays local until sent to Deepbrid AI Chat."
        )
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w", padding=5).pack(
            fill="x", side="bottom"
        )
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.configure(style="Busy.Horizontal.TProgressbar")

        self.console_panel = ttk.Frame(self.workspace, padding=(4, 2, 4, 4))
        self.console_output = tk.Text(
            self.console_panel,
            height=8,
            wrap="word",
            state="disabled",
        )
        console_scrollbar = ttk.Scrollbar(
            self.console_panel,
            orient="vertical",
            command=self.console_output.yview,
        )
        self.console_output.configure(yscrollcommand=console_scrollbar.set)
        self.console_output.pack(side="left", fill="both", expand=True)
        console_scrollbar.pack(side="right", fill="y")

    def _open_folder(self) -> None:
        selected = filedialog.askdirectory(title="Open project folder")
        if not selected:
            return
        self._load_project(Path(selected))

    def _add_additional_files(self) -> None:
        extensions = sorted(UPLOAD_FILE_EXTENSIONS | UPLOAD_IMAGE_EXTENSIONS)
        patterns = " ".join(f"*{extension}" for extension in extensions)
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="Add files to context",
            filetypes=(("Supported files", patterns), ("All files", "*.*")),
        )
        if not selected:
            return
        candidates: list[ContextFile] = []
        skipped: list[str] = []
        errors: list[str] = []
        for selected_path in selected:
            path = Path(selected_path)
            try:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("not a regular file")
                kind = upload_context_kind(path)
                if kind is None:
                    skipped.append(path.name)
                    continue
                resolved_path = path.resolve(strict=True)
            except (OSError, RuntimeError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
                continue
            candidates.append(
                ContextFile(
                    resolved_path,
                    kind,
                    external=True,
                    label=resolved_path.name,
                    show_thumbnail=False,
                )
            )
        self._include_context(candidates, skipped, errors)

    def _size_initial_panes(self, _event: tk.Event) -> None:
        if self._initial_sash_set:
            return
        width = self.main_pane.winfo_width()
        if width <= 1:
            return
        self.main_pane.sashpos(0, max(220, int(width * 0.25)))
        self._initial_sash_set = True

    def _size_project_tree(self, _event: tk.Event) -> None:
        height = self.main_pane.winfo_height()
        if height > 1:
            self.file_tree.master.rowconfigure(1, minsize=max(180, int(height * 0.45)))

    def _send_on_return(self, _event: tk.Event) -> str:
        self._send()
        return "break"

    @staticmethod
    def _insert_message_newline(event: tk.Event) -> str:
        event.widget.insert("insert", "\n")
        return "break"

    def _load_project(self, root: Path) -> None:
        if not root.is_dir():
            messagebox.showerror("Could not open folder", f"{root} is not a folder.")
            return
        try:
            root = root.resolve(strict=True)
            entries = list(iter_project_files(root))
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Could not open folder", str(error))
            return
        self.project_root = root
        self.context_files.clear()
        self.context_order.clear()
        self.context_tree_iids.clear()
        self.external_context_tree_items.clear()
        self.next_external_tree_id = 1
        self.additional_file_thumbnails.clear()
        self.additional_files_tree.delete(*self.additional_files_tree.get_children())
        self.additional_files_frame.grid_remove()
        children = self.file_tree.get_children()
        if children:
            self.file_tree.delete(*children)
        self.tree_paths.clear()
        self.tree_directories.clear()
        self.preview_path = None
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
                self.tree_directories[iid] = directory
                parent_iid = iid
            iid = f"f:{path.relative_to(root).as_posix()}"
            self.file_tree.insert(parent_iid, "end", iid=iid, text=path.name)
            self.tree_paths[iid] = path
        self._set_preview("")
        try:
            self.settings.set(LAST_PROJECT, str(self.project_root))
        except (OSError, sqlite3.Error) as error:
            self.status.set(
                f"Opened {root}, but could not save the last project setting: {error}"
            )
            return
        self.status.set(f"Opened {root}. Select files explicitly to add context.")
        self._log(f"Opened project: {root}")

    def _startup(self) -> None:
        self._startup_after_id = None
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
                self.dark_theme,
                self._set_dark_theme,
                self.wrap_text,
                self._set_wrap_text,
                self.remove_images_after_send,
                self._set_remove_images_after_send,
                self.diagnostics_enabled,
                self._set_diagnostics_enabled,
                self.output_log_path,
                self._set_output_logging,
            )
        except (OSError, sqlite3.Error) as error:
            self.status.set(f"Could not open Settings: {error}")

    def _set_auto_open_chrome(self, enabled: bool) -> None:
        self.auto_open_chrome = enabled

    def _set_dark_theme(self, enabled: bool) -> None:
        self.dark_theme = enabled
        self._apply_theme()

    def _set_wrap_text(self, enabled: bool) -> None:
        self.wrap_text = enabled
        self.preview.configure(wrap="word" if enabled else "none")

    def _set_remove_images_after_send(self, enabled: bool) -> None:
        self.remove_images_after_send = enabled

    def _mode_changed(self, _event: tk.Event) -> None:
        self.ai_mode = self.mode_selector.get()

    def _model_changed(self, _event: tk.Event) -> None:
        self.ai_model = self.model_selector.get()

    def _web_changed(self) -> None:
        self.web_enabled = self.web_var.get()

    def _set_diagnostics_enabled(self, enabled: bool) -> None:
        normalized_path = self.output_log_path.strip()
        if enabled and normalized_path:
            self._validate_output_log_path(normalized_path)
        self.diagnostics_enabled = enabled
        self.output_log_enabled = enabled and bool(normalized_path)
        self._log(
            "Diagnostics file logging enabled."
            if self.output_log_enabled
            else "Diagnostics file logging disabled."
        )

    def _set_output_logging(self, path: str) -> None:
        normalized_path = str(Path(path).expanduser()) if path.strip() else ""
        if self.diagnostics_enabled and normalized_path:
            self._validate_output_log_path(normalized_path)
        try:
            self.settings.set(OUTPUT_LOG_PATH, normalized_path)
        except (OSError, sqlite3.Error):
            raise
        self.output_log_path = normalized_path
        self.output_log_enabled = self.diagnostics_enabled and bool(normalized_path)
        self._log(
            f"Diagnostics file path set to: {normalized_path}"
            if normalized_path
            else "Diagnostics file path cleared; file logging is disabled."
        )

    def _open_sessions(self) -> None:
        if self.sessions_window is not None:
            try:
                if self.sessions_window.winfo_exists():
                    self.sessions_window.lift()
                    self._refresh_sessions()
                    return
            except tk.TclError:
                pass
        dialog = tk.Toplevel(self.root)
        dialog.title("Sessions")
        dialog.geometry("560x460")
        dialog.minsize(460, 340)
        dialog.transient(self.root)
        self.sessions_window = dialog
        self.sessions_filter.set("")
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        ttk.Label(frame, text="Search sessions").grid(
            row=0,
            column=0,
            sticky="w",
        )
        search = ttk.Entry(frame, textvariable=self.sessions_filter)
        search.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        tree = ttk.Treeview(
            frame,
            columns=("title", "updated"),
            show="headings",
            selectmode="browse",
        )
        tree.heading("title", text="Session")
        tree.heading("updated", text="Updated")
        tree.column("title", width=360, anchor="w")
        tree.column("updated", width=140, anchor="w")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        tree.bind("<Double-1>", lambda _event: self._open_selected_session())
        self.sessions_tree = tree
        self.session_rows.clear()
        self.sessions_status = tk.StringVar(master=dialog, value="Loading sessions...")
        ttk.Label(frame, textvariable=self.sessions_status).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text="Refresh",
            command=self._refresh_sessions,
        ).pack(side="left")
        ttk.Button(
            actions,
            text="New chat",
            command=self._start_new_chat,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="Open",
            command=self._open_selected_session,
        ).pack(side="right")
        ttk.Button(
            actions,
            text="Close",
            command=self._close_sessions,
        ).pack(side="right", padx=(0, 8))
        self.sessions_filter.trace_add("write", self._filter_sessions)
        dialog.protocol("WM_DELETE_WINDOW", self._close_sessions)
        dialog.bind("<Destroy>", self._on_sessions_dialog_destroy, add="+")
        dialog.grab_set()
        self._refresh_sessions()

    def _on_sessions_dialog_destroy(self, event: tk.Event) -> None:
        if self.sessions_window is not None and event.widget is self.sessions_window:
            self.sessions_window = None
            self.sessions_tree = None
            self.sessions_status = None
            self.session_rows.clear()

    def _close_sessions(self) -> None:
        if self.sessions_window is not None:
            self.sessions_window.destroy()

    def _filter_sessions(self, *_args: object) -> None:
        tree = self.sessions_tree
        if tree is None:
            return
        query = self.sessions_filter.get().casefold().strip()
        tree.delete(*tree.get_children())
        self.session_rows.clear()
        row_number = 0
        for session in self.sessions:
            if query and query not in session.title.casefold() and query not in session.updated.casefold():
                continue
            row = f"session:{row_number}"
            row_number += 1
            tree.insert(
                "",
                "end",
                iid=row,
                values=(session.title, session.updated),
                tags=("active",) if session.active else (),
            )
            self.session_rows[row] = session
        tree.tag_configure("active", font=("TkDefaultFont", 9, "bold"))

    def _refresh_sessions(self) -> None:
        if self.sessions_request_active:
            if self.sessions_status is not None:
                self.sessions_status.set("Session request already in progress...")
            return
        self._start_sessions_request("list")

    def _start_new_chat(self) -> None:
        self._start_sessions_request("new")

    def _open_selected_session(self) -> None:
        tree = self.sessions_tree
        if tree is None:
            return
        selection = tree.selection()
        if not selection:
            if self.sessions_status is not None:
                self.sessions_status.set("Select a session to open.")
            return
        session = self.session_rows.get(selection[0])
        if session is not None:
            self._start_sessions_request("open", session.session_id)

    def _start_sessions_request(self, action: str, session_id: str | None = None) -> None:
        if self.sessions_request_active:
            return
        self.sessions_request_active = True
        if self.sessions_status is not None:
            self.sessions_status.set(
                "Loading sessions..." if action == "list" else "Opening chat..."
            )
        worker = threading.Thread(
            target=self._sessions_worker,
            args=(action, session_id),
            name="deepbrid-sessions",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self.sessions_request_active = False
            if self.sessions_status is not None:
                self.sessions_status.set(f"Could not start the session request: {error}")

    def _sessions_worker(self, action: str, session_id: str | None) -> None:
        try:
            if action == "list":
                sessions = self.chat_browser.list_sessions()
                self.sessions_events.put(("sessions-list-success", sessions))
            elif action == "open" and session_id is not None:
                self.chat_browser.open_session(session_id)
                self.sessions_events.put(("sessions-action-success", "Opened session."))
            elif action == "new":
                self.chat_browser.new_chat()
                self.sessions_events.put(("sessions-action-success", "Started a new chat."))
            else:
                raise ValueError(f"Unknown session action: {action}")
        except (BrowserLaunchError, OSError, RuntimeError, ValueError) as error:
            self.sessions_events.put(("sessions-error", str(error)))

    def _poll_sessions_events(self) -> None:
        while True:
            try:
                event, content = self.sessions_events.get_nowait()
            except queue.Empty:
                break
            self.sessions_request_active = False
            if event == "sessions-list-success":
                if not isinstance(content, list) or not all(
                    isinstance(session, ChatSession) for session in content
                ):
                    if self.sessions_status is not None:
                        self.sessions_status.set("Deepbrid returned invalid session data.")
                    continue
                self.sessions = content
                self._filter_sessions()
                if self.sessions_status is not None:
                    self.sessions_status.set(f"{len(content)} session(s) loaded.")
            elif event == "sessions-action-success":
                if isinstance(content, str):
                    self.status.set(content)
                self._close_sessions()
            elif event == "sessions-error":
                message = str(content)
                if self.sessions_status is not None:
                    self.sessions_status.set(message)
                self.status.set(message)

    @staticmethod
    def _validate_output_log_path(path: str) -> None:
        if not path.strip():
            raise ValueError("Choose a log file before enabling output logging.")
        log_path = Path(path).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8"):
            pass

    def _log(self, message: str) -> None:
        line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
        with self._log_lock:
            self.console_history.append(line)
            file_error_line: str | None = None
            if self.output_log_enabled and self.output_log_path:
                try:
                    with Path(self.output_log_path).expanduser().open(
                        "a",
                        encoding="utf-8",
                    ) as log_file:
                        log_file.write(line + "\n")
                except OSError as error:
                    file_error_line = (
                        f"{datetime.now().astimezone().isoformat(timespec='seconds')} "
                        f"ERROR Could not write application log: {error}"
                    )
            self.console_events.put(line)
            if file_error_line is not None:
                self.console_history.append(file_error_line)
                self.console_events.put(file_error_line)

    def _report_callback_exception(
        self,
        exception_type: type[BaseException],
        exception: BaseException,
        exception_traceback: TracebackType | None,
    ) -> None:
        details = "".join(
            traceback.format_exception(
                exception_type,
                exception,
                exception_traceback,
            )
        ).rstrip()
        self._log(f"Unhandled UI exception:\n{details}")

    def _toggle_console(self) -> None:
        if self.console_visible:
            height = self.workspace.winfo_height()
            sash_position = self.workspace.sashpos(0)
            if height > 1 and sash_position > 0:
                self.console_sash_position = sash_position
            self._close_console()
            return
        self.workspace.add(self.console_panel, weight=1)
        self.console_visible = True
        self.root.after(50, self._restore_console_pane)
        self._poll_console_events()

    def _restore_console_pane(self) -> None:
        if not self.console_visible:
            return
        self.workspace.update_idletasks()
        height = self.workspace.winfo_height()
        if height <= 1:
            return
        if self.console_sash_position is None:
            self.console_sash_position = round(height * 2 / 3)
        self.workspace.sashpos(0, self.console_sash_position)

    def _close_console(self) -> None:
        if self.console_visible:
            self.workspace.forget(self.console_panel)
            self.console_visible = False

    def _apply_console_theme(self) -> None:
        if self.console_output is None:
            return
        colors = self.theme_colors
        self.console_output.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["foreground"],
            selectbackground=colors["selection"],
        )

    def _poll_console_events(self) -> None:
        if self.console_output is None:
            while not self.console_events.empty():
                try:
                    self.console_events.get_nowait()
                except queue.Empty:
                    break
            return
        while True:
            try:
                line = self.console_events.get_nowait()
            except queue.Empty:
                break
            try:
                self.console_output.configure(state="normal")
                self.console_output.insert("end", line + "\n")
                self.console_output.see("end")
                self.console_output.configure(state="disabled")
            except tk.TclError:
                self._close_console()
                return

    def _apply_theme(self) -> None:
        if self.dark_theme:
            colors = {
                "background": "#202522",
                "surface": "#2b332f",
                "foreground": "#e8eee9",
                "disabled_foreground": "#7f8983",
                "field": "#171c19",
                "accent": "#7898ff",
                "selection": "#2e426e",
                "border": "#56615b",
            }
        else:
            colors = {
                "background": "#f0f2f0",
                "surface": "#ffffff",
                "foreground": "#202b25",
                "disabled_foreground": "#89928c",
                "field": "#ffffff",
                "accent": "#3569f6",
                "selection": "#dbe6ff",
                "border": "#aab5c2",
            }
        self.theme_colors = colors
        self.root.configure(background=colors["background"])
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            ".",
            background=colors["background"],
            foreground=colors["foreground"],
        )
        style.configure("TFrame", background=colors["background"])
        style.configure(
            "TLabel",
            background=colors["background"],
            foreground=colors["foreground"],
        )
        style.configure(
            "TButton",
            background=colors["surface"],
            foreground=colors["foreground"],
            padding=(8, 4),
        )
        style.configure(
            "TEntry",
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            insertcolor=colors["foreground"],
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", colors["field"])],
            foreground=[("readonly", colors["foreground"])],
        )
        style.map(
            "TButton",
            background=[("active", colors["accent"]), ("disabled", colors["surface"])],
            foreground=[
                ("active", colors["foreground"]),
                ("disabled", colors["disabled_foreground"]),
            ],
        )
        style.configure(
            "TCheckbutton",
            background=colors["background"],
            foreground=colors["foreground"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", colors["background"])],
            foreground=[("disabled", colors["disabled_foreground"])],
        )
        style.configure(
            "Treeview",
            background=colors["field"],
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            rowheight=22,
        )
        style.map(
            "Treeview",
            background=[("selected", colors["selection"])],
            foreground=[("selected", colors["foreground"])],
        )
        style.configure(
            "AdditionalFiles.Treeview",
            background=colors["field"],
            fieldbackground=colors["field"],
            foreground=colors["foreground"],
            bordercolor=colors["border"],
            rowheight=40,
        )
        style.map(
            "AdditionalFiles.Treeview",
            background=[("selected", colors["selection"])],
            foreground=[("selected", colors["foreground"])],
        )
        style.configure(
            "TProgressbar",
            background=colors["accent"],
            troughcolor=colors["surface"],
            bordercolor=colors["border"],
        )
        style.configure(
            "Busy.Horizontal.TProgressbar",
            background=colors["accent"],
            troughcolor=colors["surface"],
            bordercolor=colors["border"],
        )
        self.preview.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["foreground"],
            selectbackground=colors["selection"],
        )
        self.chat_output.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["foreground"],
            selectbackground=colors["selection"],
        )
        self.message.configure(
            background=colors["field"],
            foreground=colors["foreground"],
            insertbackground=colors["foreground"],
            selectbackground=colors["selection"],
        )
        self.chat_output.tag_configure(
            "turn-separator",
            foreground=colors["accent"],
            justify="center",
            spacing1=8,
            spacing3=8,
        )
        self._apply_console_theme()
        self.file_context_menu.configure(
            background=colors["surface"],
            foreground=colors["foreground"],
            activebackground=colors["selection"],
            activeforeground=colors["foreground"],
        )
        self.additional_file_menu.configure(
            background=colors["surface"],
            foreground=colors["foreground"],
            activebackground=colors["selection"],
            activeforeground=colors["foreground"],
        )
        self.logo_image = create_brand_icon(self.root, self.dark_theme, 48)
        self.logo_label.configure(image=self.logo_image)
        self._set_window_icons()

    def _set_window_icons(self) -> None:
        self.window_icons = tuple(
            create_brand_icon(self.root, self.dark_theme, size)
            for size in (16, 32, 48)
        )
        self.root.iconphoto(True, *self.window_icons)
        self.root.iconbitmap(str(APP_ICON_PATH))

    def _show_file_context_menu(self, event: tk.Event) -> str:
        row = self.file_tree.identify_row(event.y)
        if not row or (row not in self.tree_paths and row not in self.tree_directories):
            return "break"
        if row not in self.file_tree.selection():
            self.file_tree.selection_set(row)
            self.file_tree.focus(row)
        selected_rows = set(self.file_tree.selection())
        has_selected_context = bool(self._context_keys_for_project_rows(selected_rows))
        self.file_context_menu.delete(0, "end")
        self.file_context_menu.add_command(
            label="Add selected to context",
            command=self._add_context,
        )
        if has_selected_context:
            self.file_context_menu.add_command(
                label="Remove selected from context",
                command=self._remove_selected_context,
            )
        self.file_context_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _context_keys_for_project_rows(self, rows: set[str]) -> list[str]:
        selected_files = {
            path.resolve(strict=False)
            for row, path in self.tree_paths.items()
            if row in rows
        }
        selected_directories = [
            path for row, path in self.tree_directories.items() if row in rows
        ]
        return [
            key
            for key, item in self.context_files.items()
            if not item.external
            and (
                item.path.resolve(strict=False) in selected_files
                or any(
                    self._is_context_under_directory(item, directory)
                    for directory in selected_directories
                )
            )
        ]

    def _is_context_under_directory(self, item: ContextFile, directory: Path) -> bool:
        if item.external or self.project_root is None:
            return False
        try:
            item.path.resolve(strict=False).relative_to(directory.resolve(strict=False))
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def _show_additional_file_menu(self, event: tk.Event) -> str:
        row = self.additional_files_tree.identify_row(event.y)
        if not row:
            return "break"
        if row not in self.additional_files_tree.selection():
            self.additional_files_tree.selection_set(row)
        self.additional_file_menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _start_progress(self) -> None:
        if not self.progress.winfo_manager():
            self.progress.pack(fill="x", side="bottom")
        self.progress.start(12)

    def _stop_progress(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()

    def _preview_selection(self, _event: tk.Event) -> None:
        selection = self.file_tree.selection()
        if not selection:
            return
        path = self.tree_paths.get(selection[0])
        if path is None:
            return
        self.preview_path = path
        try:
            kind = upload_context_kind(path)
        except (OSError, ValueError) as error:
            self._set_preview(f"Could not inspect {path.name}: {error}")
            return
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
                with Image.open(path) as image:
                    image.thumbnail((220, 180))
                    self.preview_image = ImageTk.PhotoImage(image.copy(), master=self.root)
                self.preview_image_label.configure(image=self.preview_image, text="")
            except (OSError, RuntimeError, ValueError, tk.TclError) as error:
                self.preview_image = None
                self.preview_image_label.configure(
                    image="",
                    text=f"Preview unavailable ({error}); the image can still be selected.",
                )
        elif kind == "file":
            self.preview_image = None
            self.preview_image_label.configure(image="", text="")
            self._set_preview(f"Attached file: {path.name}")
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
            self.status.set("Select one or more files or folders to add context.")
            return
        candidates: list[ContextFile] = []
        skipped: list[str] = []
        errors: list[str] = []
        directories: list[Path] = []
        for iid in selected_items:
            directory = self.tree_directories.get(iid)
            if directory is not None:
                directories.append(directory)
                continue
            path = self.tree_paths.get(iid)
            if path is None:
                continue
            try:
                if path.is_symlink():
                    raise ValueError(f"{path.name} became a symbolic link.")
                kind = upload_context_kind(path)
            except (OSError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
                continue
            if kind is None:
                skipped.append(path.name)
                continue
            try:
                resolved_path = path.resolve(strict=True)
                relative_path = resolved_path.relative_to(self.project_root)
            except (OSError, RuntimeError, ValueError) as error:
                errors.append(f"{path.name}: {error}")
                continue
            candidates.append(ContextFile(resolved_path, kind, label=relative_path.as_posix()))
        ignored_count = 0
        for directory in directories:
            try:
                resolved_directory = directory.resolve(strict=True)
                relative_directory = resolved_directory.relative_to(self.project_root)
                files = list(iter_project_files(resolved_directory))
            except (OSError, RuntimeError, ValueError) as error:
                errors.append(f"{directory.name}: {error}")
                self._log(f"Could not inspect context directory {directory}: {error}")
                continue
            for path in files:
                try:
                    kind = upload_context_kind(path)
                    if kind is None:
                        ignored_count += 1
                        continue
                    resolved_path = path.resolve(strict=True)
                    relative_path = resolved_path.relative_to(self.project_root)
                except (OSError, RuntimeError, ValueError) as error:
                    errors.append(f"{path.name}: {error}")
                    continue
                candidates.append(
                    ContextFile(resolved_path, kind, label=relative_path.as_posix())
                )
            self._log(
                f"Added supported files from directory {relative_directory.as_posix()}."
            )
        if ignored_count:
            skipped.append(f"Ignored {ignored_count} unsupported file(s)")
        if not candidates and not skipped and not errors:
            skipped.append("No eligible files found in the selection")
        self._include_context(candidates, skipped, errors)

    def _include_context(
        self,
        candidates: list[ContextFile],
        skipped: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        skipped = skipped or []
        errors = errors or []
        added: list[str] = []
        for item in candidates:
            key = str(item.path)
            if key in self.context_files:
                continue
            self.context_files[key] = item
            self.context_order.append(key)
            self._mark_context_in_tree(key, item)
            added.append(item.path.name)
            self._log(f"Added context: {item.label or item.path.name} ({item.kind}).")
        messages: list[str] = []
        if added:
            messages.append(
                f"Added {', '.join(added)} to included context "
                f"({len(self.context_files)} item(s) total)."
            )
        if skipped:
            messages.append(
                f"Skipped unsupported item(s): {', '.join(skipped)}."
            )
        if errors:
            messages.append(f"Could not add file(s): {'; '.join(errors)}")
        if not messages:
            messages.append(
                f"Selected file(s) already included. "
                f"{len(self.context_files)} context item(s) total."
            )
        self.status.set(" ".join(messages))

    def _mark_context_in_tree(self, key: str, item: ContextFile) -> None:
        if item.external:
            iid = f"context:additional:{self.next_external_tree_id}"
            self.next_external_tree_id += 1
            has_thumbnail = item.kind == "image" and item.show_thumbnail
            label = (
                item.label or item.path.name
                if has_thumbnail
                else self._truncate_additional_path(item.path)
            )
            thumbnail: ImageTk.PhotoImage | None = None
            if has_thumbnail:
                try:
                    with Image.open(item.path) as image:
                        image.thumbnail((48, 36))
                        thumbnail = ImageTk.PhotoImage(image.copy(), master=self.root)
                except (OSError, RuntimeError, ValueError) as error:
                    self._log(f"Could not create image thumbnail {item.path.name}: {error}")
            insert_options: dict[str, object] = {
                "iid": iid,
                "text": f"* {label}",
            }
            if thumbnail is not None:
                insert_options["image"] = thumbnail
            self.additional_files_tree.insert("", "end", **insert_options)
            if thumbnail is not None:
                self.additional_file_thumbnails[iid] = thumbnail
            self.additional_files_label.configure(
                text=f"Additional files ({len(self.external_context_tree_items) + 1})"
            )
            self.additional_files_frame.grid()
            self.external_context_tree_items[iid] = item
        else:
            iid = next(
                (
                    tree_iid
                    for tree_iid, path in self.tree_paths.items()
                    if path == item.path
                ),
                None,
            )
            if iid is not None:
                self.file_tree.item(
                    iid,
                    text=f"* {item.label or item.path.name}",
                )
        if iid is not None:
            self.context_tree_iids[key] = iid

    def _truncate_additional_path(self, path: Path) -> str:
        width = max(80, self.additional_files_tree.winfo_width() - 90)
        font = tkfont.nametofont("TkDefaultFont")
        filename = path.name
        prefix = f"{path.parent}{os.sep}"
        while prefix and font.measure(f"...{prefix}{filename}") > width:
            prefix = prefix[1:]
        return f"...{prefix}{filename}" if prefix else filename

    def _refresh_additional_file_labels(self, _event: tk.Event) -> None:
        for iid, item in self.external_context_tree_items.items():
            if item.kind != "image" or not item.show_thumbnail:
                self.additional_files_tree.item(
                    iid,
                    text=f"* {self._truncate_additional_path(item.path)}",
                )

    def _paste_clipboard_image(self, _event: tk.Event) -> str | None:
        try:
            clipboard_content = ImageGrab.grabclipboard()
        except OSError as error:
            self.status.set(f"Could not read the clipboard image: {error}")
            clipboard_content = None

        source_image: Image.Image | None = None
        if isinstance(clipboard_content, Image.Image):
            source_image = clipboard_content
        else:
            image_path = self._clipboard_image_path(clipboard_content)
            if image_path is None:
                image_path = self._clipboard_text_image_path()
            if image_path is None:
                return None
            try:
                with Image.open(image_path) as image:
                    source_image = image.convert("RGBA")
            except (OSError, ValueError) as error:
                self.status.set(f"Could not read clipboard image {image_path.name}: {error}")
                return "break"

        if source_image is None:
            return None
        try:
            self._save_clipboard_image(source_image)
        except (OSError, ValueError) as error:
            self.status.set(f"Could not save clipboard image: {error}")
            return "break"
        return "break"

    @staticmethod
    def _clipboard_image_path(content: object) -> Path | None:
        if not isinstance(content, (list, tuple)):
            return None
        for value in content:
            if not isinstance(value, str):
                continue
            path = Path(value)
            try:
                if path.is_file() and context_kind(path) == "image":
                    return path
            except (OSError, ValueError):
                continue
        return None

    def _clipboard_text_image_path(self) -> Path | None:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return None
        candidate = text.strip().strip('"')
        if not candidate:
            return None
        path = Path(candidate)
        try:
            if path.is_file() and context_kind(path) == "image":
                return path
        except (OSError, ValueError):
            return None
        return None

    def _save_clipboard_image(self, image: Image.Image) -> None:
        if self.clipboard_image_directory is None:
            self.clipboard_image_directory = tempfile.TemporaryDirectory(
                prefix="deepbrid-code-clipboard-"
            )
        image_path = (
            Path(self.clipboard_image_directory.name)
            / f"clipboard-{len(self.clipboard_images) + 1}.png"
        )
        image.convert("RGBA").save(image_path, format="PNG")
        if image_path.stat().st_size > MAX_IMAGE_PREVIEW_BYTES:
            image_path.unlink()
            self.status.set(
                f"Clipboard image exceeds the {MAX_IMAGE_PREVIEW_BYTES // (1024 * 1024)} MiB limit."
            )
            return

        self.clipboard_images.add(image_path)
        self._include_context(
            [
                ContextFile(
                    image_path,
                    "image",
                    external=True,
                    label=f"Clipboard image {len(self.clipboard_images)}",
                )
            ]
        )

    def _remove_selected_context(self) -> None:
        selected_rows = set(self.file_tree.selection())
        keys = self._context_keys_for_project_rows(selected_rows)
        selected_images = set(self.additional_files_tree.selection())
        keys.extend(
            key
            for key, tree_iid in self.context_tree_iids.items()
            if tree_iid in selected_images and key not in keys
        )
        self._remove_context_keys(keys)

    def _remove_context_keys(self, keys: list[str]) -> None:
        removed = 0
        for key in keys:
            iid = self.context_tree_iids.get(key)
            if iid is None:
                continue
            item = self.context_files[key]
            self.context_tree_iids.pop(key, None)
            self.context_files.pop(key, None)
            self.context_order.remove(key)
            if item.external:
                self.external_context_tree_items.pop(iid, None)
                self.additional_file_thumbnails.pop(iid, None)
                self.additional_files_tree.delete(iid)
                self.additional_files_label.configure(
                    text=f"Additional files ({len(self.external_context_tree_items)})"
                )
            else:
                if self.file_tree.exists(iid):
                    self.file_tree.item(iid, text=item.path.name)
            if self.preview_path == item.path:
                self.preview_path = None
                self.preview_image = None
                self.preview_image_label.configure(image="", text="")
                self._set_preview("")
            self._log(f"Removed context: {item.label or item.path.name}.")
            removed += 1
        if not self.external_context_tree_items:
            self.additional_files_frame.grid_remove()
        self.status.set(
            f"Removed {removed} context item(s). "
            f"{len(self.context_files)} item(s) remain included."
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

        attachment_paths = [
            item.path
            for item in self.context_files.values()
            if item.kind in {"image", "file"}
        ]
        external_attachment_paths = [
            item.path
            for item in self.context_files.values()
            if item.kind in {"image", "file"} and item.external
        ]
        self.pending_image_context_keys = [
            key
            for key, item in self.context_files.items()
            if item.kind == "image"
        ]
        self.pending_remove_images_after_send = self.remove_images_after_send
        selected_model = self.model_selector.get()
        selected_mode = self.mode_selector.get()
        web_enabled = self.web_var.get()
        self.ai_model = selected_model
        self.ai_mode = selected_mode
        self.web_enabled = web_enabled
        self.chat_request_active = True
        self._log(
            f"Sending prompt with {len(self.context_files)} context item(s) "
            f"and {len(attachment_paths)} attachment(s), model {selected_model}, "
            f"mode {selected_mode}, Web {'on' if web_enabled else 'off'}."
        )
        self._append_chat("You", prompt)
        if attachment_paths:
            self._append_chat(
                "Files attached",
                "\n".join(path.name for path in attachment_paths),
            )
        self.message.delete("1.0", "end")
        self.status.set("Sending message to Deepbrid AI Chat. Waiting for its response...")
        self._start_progress()
        worker = threading.Thread(
            target=self._chat_worker,
            args=(
                prompt,
                attachment_paths,
                self.project_root,
                external_attachment_paths,
                selected_model,
                selected_mode,
                web_enabled,
            ),
            name="deepbrid-chat-ui",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self.chat_request_active = False
            self.pending_image_context_keys = []
            self._stop_progress()
            self.status.set(f"Could not start the chat request: {error}")

    def _chat_worker(
        self,
        prompt: str,
        attachment_paths: list[Path],
        project_root: Path | None,
        external_attachment_paths: list[Path],
        model: str,
        mode: str,
        web_enabled: bool,
    ) -> None:
        try:
            response = self.chat_browser.send_message(
                prompt,
                attachment_paths,
                project_root,
                external_attachment_paths,
                on_submitted=lambda: self.chat_events.put(("chat-submitted", "")),
                model=model,
                mode=mode,
                web_enabled=web_enabled,
            )
        except BrowserLaunchError as error:
            self._log(f"Chat request failed: {error}")
            self.chat_events.put(("chat-error", str(error)))
        except (OSError, ValueError, RuntimeError) as error:
            self._log(f"Chat operation failed: {error}")
            self.chat_events.put(("chat-error", f"Chat operation failed: {error}"))
        else:
            self.chat_events.put(("chat-success", response))
        finally:
            if self.cleanup_clipboard_after_chat:
                self._cleanup_clipboard_images()

    def _poll_chat_events(self) -> None:
        self._poll_after_id = None
        while True:
            try:
                event, content = self.chat_events.get_nowait()
            except queue.Empty:
                break
            if event in {"chat-success", "chat-error"}:
                self.chat_request_active = False
                self._stop_progress()
            elif event.startswith("browser-"):
                self.browser_request_active = False
                self._stop_progress()
            if event == "chat-success":
                self._log(f"Deepbrid AI Chat returned {len(content)} characters.")
                self._append_chat("Deepbrid AI", content)
                self.status.set(f"Deepbrid AI Chat replied ({len(content)} characters).")
            elif event == "chat-error":
                self._append_chat("Deepbrid AI Chat status", content)
                self.status.set(content)
            elif event == "chat-submitted":
                if self.pending_remove_images_after_send:
                    self._remove_context_keys(self.pending_image_context_keys)
                self.pending_image_context_keys = []
            elif event == "browser-chat":
                self._log("Deepbrid AI Chat is open and ready.")
                self.status.set("Deepbrid AI Chat is open and ready.")
            elif event == "browser-login":
                self._log("Chrome is open to Deepbrid login.")
                self.status.set("Chrome is open to Deepbrid login. Sign in, then send your message.")
            elif event == "browser-error":
                self.status.set(content)
        self._poll_console_events()
        self._poll_sessions_events()
        self._poll_after_id = self.root.after(200, self._poll_chat_events)

    def _on_root_destroy(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        for callback_id in (self._poll_after_id, self._startup_after_id):
            if callback_id is not None:
                try:
                    self.root.after_cancel(callback_id)
                except tk.TclError:
                    pass
        self._poll_after_id = None
        self._startup_after_id = None
        if self.root.report_callback_exception == self._report_callback_exception:
            self.root.report_callback_exception = self._previous_callback_exception

    def _append_chat(self, speaker: str, content: str) -> None:
        self.chat_output.configure(state="normal")
        if speaker == "You":
            timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            self.chat_output.insert(
                "end",
                f"-------------------- {timestamp} --------------------\n",
                "turn-separator",
            )
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
        self._start_progress()
        worker = threading.Thread(
            target=self._browser_worker,
            name="deepbrid-chat-browser",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            self.browser_request_active = False
            self._stop_progress()
            self.status.set(f"Could not start Chrome: {error}")

    def _browser_worker(self) -> None:
        try:
            landing_page = self.chat_browser.open_for_chat()
        except (BrowserLaunchError, OSError, RuntimeError) as error:
            self._log(f"Could not open Deepbrid AI Chat: {error}")
            self.chat_events.put(("browser-error", f"Could not open Deepbrid AI Chat: {error}"))
        else:
            self.chat_events.put((f"browser-{landing_page}", ""))

    def _close(self) -> None:
        self._log("Deepbrid Code is closing.")
        if self.chat_request_active:
            self.cleanup_clipboard_after_chat = True
        else:
            self._cleanup_clipboard_images()
        if self.console_visible:
            self._close_console()
        self.root.destroy()

    def _cleanup_clipboard_images(self) -> None:
        if self.clipboard_image_directory is not None:
            self.clipboard_image_directory.cleanup()
            self.clipboard_image_directory = None
            self.clipboard_images.clear()


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
