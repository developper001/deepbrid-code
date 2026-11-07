# Deepbrid Code

Deepbrid Code is a local-first Windows coding-assistant shell built with Python
and Tkinter. It can open a project folder, preview text files and images, and
prepare selected context for use in Deepbrid AI Chat.

![Deepbrid Code showing the project explorer, file preview, and AI chat](src\img\screenshots\DeepbridCode.png)

## Run

Requires Python 3.11 or newer with Tkinter available:

```powershell
python -m pip install -r requirements.txt
python -m src.app
```

Run the tests with:

```powershell
python -m unittest discover -s tests -v
```

## Current chat limitations

The documented Deepbrid API does not provide a public AI-chat endpoint. This
app controls the dedicated Chrome profile through Chrome's loopback-only
DevTools interface and interacts with the visible AI Chat page; it does not
call or reverse-engineer private chat endpoints.

**Open Deepbrid AI Chat** launches Google Chrome with a separate profile under
`%LOCALAPPDATA%\Deepbrid Code\chrome-profile`. Sign in yourself in that window.
Chrome opens the AI Chat page when the profile is signed in; if not, Deepbrid's
login page is opened. By default, the profile is started automatically when the
app opens; change this in **Settings**.
The app does not read, copy, or transmit browser cookies, passwords, or session
tokens. The app can control that dedicated browser profile while it is running;
the debugging port listens only on `127.0.0.1`. **Send** immediately submits the
message and explicitly selected context through the visible chat UI. Supported
documents and images are attached through the site's file-upload control. The
app shows a busy indicator while waiting and displays either the rendered
response or an error/timeout in the conversation and status bar.
If Chrome is installed in a non-standard location, set
`DEEPBRID_CHROME_PATH` to its executable before launching the app.
The progress bar is shown only while Chrome is opening or a chat request is in
progress.

This UI integration is necessarily brittle: Deepbrid may change its chat page,
which can require updating the visible-control selectors. If the page cannot
be recognized or a response is not received, the app reports the failure and
leaves the browser available for manual use. It does not inspect network
requests or depend on undocumented chat APIs.

The app stores preferences in `%LOCALAPPDATA%\Deepbrid Code\settings.sqlite3`,
including the automatic Chrome setting, dark theme choice, and last opened
project folder. Select a model, assistant mode, and optional **Web** search
beside the message controls; the default mode is **Code Assistant** and Web
search is off. These choices are applied through the visible Deepbrid controls
when sending a message.

Use **Sessions** to search the sessions currently available in Deepbrid, open a
selected chat, or start a new one. Session history is read from the signed-in
Deepbrid page and is not copied into local storage.

## Privacy and project files

Opening a folder only lists local files; it does not upload or modify them.
Common generated and dependency directories such as `.git`, `node_modules`,
`build`, and `dist` are omitted. Only files you explicitly add appear in the
included context. A leading `*` in the project tree marks files that will be
sent. Avoid selecting secrets or sensitive project content. Text
context is limited to 256 KiB per file and
1 MiB total. Image previews use the formats supported by the installed Tk
build and are limited to 20 MiB; selected images larger than that are not
attached by the app.

## Using included context

1. Open a project folder. Select a file in **Project files** to preview it.
2. Right-click a file and choose **Add selected to context**. The app attaches
   files with extensions supported by Deepbrid, including images; for other
   extensions it checks contents, includes text files such as `LICENSE`, and
   refuses unrecognized binary files. Right-click a directory or selected
   files and folders and choose **Add selected to context** to include all
   supported files and eligible text files recursively. Added files are marked
   with `*` in the project tree. Selecting or previewing a file alone does not
   include or send it.
3. Right-click a marked file or selected folder(s) and choose
   **Remove selected from context** to exclude the selected files and all
   included files beneath the selected folders. This option appears only when
   the selection contains context.
4. Enter your question in **Message** and choose **Send**, or press Enter to
   send the message and listed context. Use Ctrl+Enter to insert a newline.

Included context is kept locally in the app until you send a prompt.
Files with extensions accepted by the site are attached directly; other files
are checked by their contents and recognized text is included with its path and
contents. The site currently accepts PDF, DOCX, XLSX, PPTX, ODT, ODS, ODP,
TXT, TEXT, MD, MARKDOWN, CSV, TSV, JSON, JSONL, XML, HTML, HTM, LOG, YAML, YML,
INI, CONF, CFG, TOML, ENV, SQL, PHP, JS, MJS, CJS, TS, TSX, JSX, PY, RB, GO,
RS, JAVA, KT, KTS, SWIFT, C, H, CPP, CC, CXX, HPP, CS, M, SCALA, SH, BASH,
ZSH, PS1, BAT, CMD, R, LUA, PL, DART, VUE, SVELTE, CSS, SCSS, SASS, LESS,
TEX, SRT, VTT, GRADLE, GRAPHQL, PROTO, and images (`image/*`).

Use **Add files...** to choose supported files from outside the project. These
appear in **Additional files** with their paths (trimmed from the beginning to
keep each filename visible); no preview is shown for files added this way.
Images and manually added files are sent as attachments. Project files keep
the `*` marker in the tree.

By default, images are removed from included context after Deepbrid confirms
the message was submitted; change **Remove images from context after sending**
in **Settings** to retain them. Other context remains available for reuse.
Review marked files before sending, especially for secrets. Text included
inline has a 256 KiB per-file limit and 1 MiB total limit. Image attachments
have a 20 MiB limit; non-image attachment size limits are enforced by Deepbrid.

You can paste a screenshot from the clipboard into the **Message** box with
Ctrl+V. Clipboard screenshots and manually added images appear in the
**Additional files** section below the project tree. Pasted images appear as
thumbnails; manually added files show a shortened path. Right-click an item to
remove it. Pasting does not send anything by itself. Pasted images are held in
a temporary local folder and removed when the app closes.

The app opens at 1180x760, with the project files pane using about one quarter
of the window width and most space reserved for chat. Each prompt in the
in-memory conversation is preceded by a timestamped separator.

## Console and preferences

Use **Toggle Console** to show or hide timestamped application diagnostics and
errors in a resizable panel at the bottom of the window. The console keeps the
latest messages in memory while the app is running. File diagnostics are
disabled by default. In **Settings**, enable **Enable diagnostics file logging**
to append diagnostics to the path shown there; the default path is
`diagnostics\deepbrid-code.log` in the project folder. The checkbox and path
are independent: logging is active only when enabled and the path is nonempty.
Clearing the path disables file logging without removing the checkbox setting.

The app remembers the last project folder and reopens it next time. These
preferences, the automatic Chrome startup setting, dark theme choice, and
image-removal preference are stored in SQLite at
`%LOCALAPPDATA%\Deepbrid Code\settings.sqlite3`. Automatic Chrome startup is
enabled by default and can be changed in **Settings**. Toggle **Use dark mode**
there to switch and save the app's appearance.
**Wrap text in file preview** is enabled by default and saved in the same
settings database. Turn it off to use the preview's horizontal scrollbar;
vertical and horizontal scrollbars are available in the preview.

The app does not impose a separate character limit on the message field. Text
context has a 256 KiB per-file limit and a 1 MiB total limit. Deepbrid AI Chat's
maximum accepted message length is not documented here, so very large prompts
may still be rejected or truncated by the website.

Official API transport and richer project navigation are not implemented.
