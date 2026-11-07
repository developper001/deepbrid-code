# Project handoff: Deepbrid Code

Use this prompt to resume work on the project in a new coding-assistant session.

## Goal

Build a small, local-first coding assistant/IDE for Windows, published in
`https://github.com/developper001/deepbrid-code`. Users should be able to:

- Open or add a project folder and select individual files as context.
- Attach images as context.
- Chat with a coding assistant that can explain, review, and help debug code.
- Launch a dedicated Chrome profile to Deepbrid AI Chat so the user can sign in
  themselves if needed.

Keep the initial implementation small and usable. Inspect the existing project
and its conventions before choosing a framework or adding dependencies.

## Findings so far

- The public Deepbrid API documentation is at `https://www.deepbrid.com/api-docs`.
  The documented `/api/v1` endpoints cover download links, account information,
  downloads, and torrents. No public AI-chat endpoint was found there.
- Deepbrid AI Chat is at `https://www.deepbrid.com/ai-chat`. The page showed a
  Code Assistant and model choices, but this does not establish a supported
  programmatic chat API.
- The repository was cloned to `C:\Users\l\Dev\deepbrid-code`. At handoff, it
  contains only `LICENSE` and this prompt; the initial commit is on `main`.
- The existing `C:\Users\l\Dev\Deepbrid-Downloader` project may contain a
  precedent for opening Chrome with a dedicated profile. Inspect that
  implementation before reusing or adapting it.

## Important constraints

- Do not assume the regular Deepbrid API key authorizes AI Chat.
- Prefer an officially documented AI endpoint if one becomes available.
- If the only available option is the website, keep authentication user-driven:
  open a dedicated Chrome profile and let the user log in. Do not copy, extract,
  persist, or transmit browser cookies, passwords, or session tokens.
- Treat website UI automation as a potentially brittle integration. Check
  applicable terms and keep the user informed about what content will be sent.
- Send only context the user explicitly selects. Make the included files and
  images visible before sending; avoid secrets and common generated/dependency
  folders by default. Do not modify project files without an explicit user
  action.
- Never put API keys or other credentials in source control, logs, or prompts.

## Suggested next steps

1. Inspect this repository, its Git status, and the Chrome-profile launch
   approach in `C:\Users\l\Dev\Deepbrid-Downloader`.
2. Determine a minimal app architecture that supports a local file tree,
   selected text/image context, and a chat panel.
3. Validate whether Deepbrid AI Chat can be used through a user-visible,
   user-authenticated browser workflow without extracting credentials. If not,
   implement the IDE shell and context management behind a clean provider
   boundary, and clearly explain that chat transport needs a supported API.
4. Implement a small end-to-end vertical slice, document setup and limitations,
   and run the project's targeted checks.

## Acceptance criteria for an initial version

- The app can open a folder and display its files without uploading them
  automatically.
- Users can select and inspect text files and images to include in a message.
- The chat transport is explicit about whether it uses a supported API or the
  logged-in website, and reports failures rather than pretending a message was
  sent.
- A button can open Deepbrid AI Chat in a dedicated Chrome profile without
  exposing browser credentials to the app.
- Setup, security/privacy behavior, and current limitations are documented.
