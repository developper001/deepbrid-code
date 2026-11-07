# Deepbrid Code

Deepbrid Code is a local-first Windows coding-assistant shell built with Python
and Tkinter. It can open a project folder, preview text files and images, and
prepare selected context for use in Deepbrid AI Chat.

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
the debugging port listens only on `127.0.0.1`. **Send to Deepbrid AI Chat**
immediately submits the message and explicitly selected context through the
visible chat UI; selected images are attached through the site's file-upload
control. The app shows a busy indicator while waiting and displays either the
rendered response or an error/timeout in the conversation and status bar.
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
project folder.

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
2. Right-click a file and choose **Add selected to context**. The app checks
   file contents rather than relying on the extension: text files such as
   `LICENSE` are included, recognized images are attached as images, and binary
   files are refused. Right-click a directory and choose
   **Add text files in directory to context** to include its recursively found
   text files; non-text files are checked and ignored. Added files are marked
   with `*` in the project tree. Selecting or previewing a file alone does not
   include or send it.
3. Right-click a marked file and choose **Remove selected from context** to
   exclude it. Right-click a directory and choose
   **Remove directory contents from context** to exclude all included files
   beneath it.
4. Enter your question in **Message**, then choose **Send to Deepbrid AI Chat**
   to send the message and listed context.

Included context is kept locally in the app until you send a prompt.
When sent, selected text is included with its file path and contents, and
selected images are attached through the chat page's file-upload control.
Included context is not cleared after sending, so you can reuse or remove items
for later messages. Review marked files before sending, especially for secrets;
see the per-file and total text limits above.

You can paste a screenshot from the clipboard into the **Message** box with
Ctrl+V. Clipboard screenshots and copied image-file paths appear as thumbnails
in the **Pasted images** section below the project tree, and are attached with
your next message; right-click an image to remove it. Pasting does not send
anything by itself. Pasted images are held in a temporary local folder and
removed when the app closes.

The app opens at 1180x760, with the project files pane using about one quarter
of the window width and most space reserved for chat. Each prompt in the
in-memory conversation is preceded by a timestamped separator.

## Console and preferences

Open **Console** to view timestamped application diagnostics and errors in a
resizable panel at the bottom of the window. The console keeps the latest
messages in memory while the app is running. To retain them across runs, set a
log file path in **Settings**; file logging is enabled whenever the path is
nonempty. Use **Clear** to remove the path and disable file logging.

The app remembers the last project folder and reopens it next time. Both
preferences, the automatic Chrome startup setting, and the dark theme choice
are stored in SQLite at
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
