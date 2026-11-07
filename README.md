# Deepbrid Code

Deepbrid Code is an early, local-first Windows coding-assistant shell built with
Python and Tkinter. It can open a project folder, preview text files and images,
and prepare selected context for use in Deepbrid AI Chat.

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
**Copy prompt for Deepbrid AI Chat** remains available for manual use. If
Chrome is installed in a non-standard location, set
`DEEPBRID_CHROME_PATH` to its executable before launching the app.

This UI integration is necessarily brittle: Deepbrid may change its chat page,
which can require updating the visible-control selectors. If the page cannot
be recognized or a response is not received, the app reports the failure and
leaves the browser available for manual use. It does not inspect network
requests or depend on undocumented chat APIs.

The app stores preferences in `%LOCALAPPDATA%\Deepbrid Code\settings.sqlite3`,
including the automatic Chrome setting and the last opened project folder.

## Privacy and project files

Opening a folder only lists local files; it does not upload or modify them.
Common generated and dependency directories such as `.git`, `node_modules`,
`build`, and `dist` are omitted. Only files you explicitly add appear in the
context list. Avoid selecting secrets or sensitive project content. Text
context is limited to 256 KiB per file and
1 MiB total. Image previews use the formats supported by the installed Tk
build and are limited to 20 MiB; selected images larger than that are not
attached by the app.

## Using included context

1. Open a project folder. Select a file in **Project files** to preview it.
2. Select one or more files (Ctrl-click or Shift-click for multiple selection)
   and click **Add selected to context**. Supported text files and images then
   appear in **Included context**, along with their project-relative paths and
   types. Selecting or previewing a file alone does not include or send it.
3. To exclude an item, select it in **Included context** and click
   **Remove selected context**.
4. Enter your question in **Message**, then choose **Send to Deepbrid AI Chat**
   to send the message and listed context, or **Copy prompt for Deepbrid AI
   Chat** to copy the text prompt for manual use.

Included context is kept locally in the app until you send or copy a prompt.
When sent, selected text is included with its file path and contents, and
selected images are attached through the chat page's file-upload control.
Copying a prompt includes text context; attach any selected images manually in
the browser. The context list is not cleared after sending, so you can reuse or
remove items for later messages. Review the list before sending, especially
for secrets; see the per-file and total text limits above.

## Preferences

The app remembers the last project folder and reopens it next time. Both
preferences and the automatic Chrome startup setting are stored in SQLite at
`%LOCALAPPDATA%\Deepbrid Code\settings.sqlite3`. Automatic Chrome startup is
enabled by default and can be changed in **Settings**.

Official API transport and richer project navigation are not implemented.
