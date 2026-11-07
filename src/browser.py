from __future__ import annotations

from collections import Counter
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websocket


AI_CHAT_URL = "https://www.deepbrid.com/ai-chat"
DEBUG_PORT_FILE = "DeepbridDevToolsPort"
DEBUGGER_TIMEOUT = 20
RESPONSE_TIMEOUT = 120
MAX_IMAGE_ATTACHMENT_BYTES = 20 * 1024 * 1024


class BrowserLaunchError(RuntimeError):
    pass


class DeepbridChatBrowser:
    def __init__(self, profile_dir: Path, browser_path: str | None = None) -> None:
        self.profile_dir = profile_dir
        self.browser_path = browser_path
        self._process: subprocess.Popen[bytes] | None = None

    def open(self) -> None:
        port = self._debug_port()
        if port is not None and self._find_deepbrid_target(port) is not None:
            return
        if self._process is not None and self._process.poll() is None:
            return
        browser = self.browser_path or self._find_chrome()
        if browser is None:
            raise BrowserLaunchError(
                "Google Chrome was not found. Install Chrome, or set DEEPBRID_CHROME_PATH "
                "to its executable."
            )
        try:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            port = self._find_free_port()
            port_file = self.profile_dir / DEBUG_PORT_FILE
            port_file.write_text(str(port), encoding="ascii")
            arguments = [
                browser,
                f"--user-data-dir={self.profile_dir}",
                f"--remote-debugging-port={port}",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                AI_CHAT_URL,
            ]
            options: dict[str, object] = {
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "close_fds": True,
            }
            if sys.platform == "win32":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._process = subprocess.Popen(arguments, **options)
        except OSError as error:
            (self.profile_dir / DEBUG_PORT_FILE).unlink(missing_ok=True)
            raise BrowserLaunchError(f"Could not start the dedicated Chrome browser: {error}") from error

    def open_for_chat(self) -> str:
        self.open()
        port = self._wait_for_debug_port()
        target = self._wait_for_deepbrid_target(port)
        if target is None:
            raise BrowserLaunchError(
                "Deepbrid AI Chat did not load. Check the dedicated Chrome window and retry."
            )
        websocket_url = target["webSocketDebuggerUrl"]
        page = self._evaluate(websocket_url, "({url:location.href,path:location.pathname})")
        if not isinstance(page, dict):
            raise BrowserLaunchError("Could not determine which Deepbrid page is open.")
        if str(page.get("path", "")).rstrip("/") == "/login":
            return "login"
        if str(page.get("path", "")).rstrip("/") != "/ai-chat":
            self._send_command(
                websocket_url,
                "Page.navigate",
                {"url": AI_CHAT_URL},
            )

        deadline = time.monotonic() + DEBUGGER_TIMEOUT
        while time.monotonic() < deadline:
            page = self._evaluate(websocket_url, "({url:location.href,path:location.pathname})")
            if isinstance(page, dict) and str(page.get("path", "")).rstrip("/") == "/login":
                return "login"
            if isinstance(page, dict) and str(page.get("path", "")).rstrip("/") == "/ai-chat":
                ready = self._evaluate(websocket_url, self._chat_ready_script())
                if isinstance(ready, dict) and ready.get("ready") is True:
                    return "chat"
            time.sleep(0.25)
        self._send_command(
            websocket_url,
            "Page.navigate",
            {"url": "https://www.deepbrid.com/login"},
        )
        login_target = self._wait_for_deepbrid_target(port, path="/login")
        if login_target is None:
            raise BrowserLaunchError(
                "Deepbrid AI Chat is not signed in, and its login page did not load."
            )
        return "login"

    def _navigate_to_chat(self, port: int) -> dict[str, str]:
        target = self._find_deepbrid_target(port)
        if target is None:
            raise BrowserLaunchError(
                "The dedicated Chrome window is not on Deepbrid. Open Deepbrid AI Chat first."
            )
        websocket_url = target["webSocketDebuggerUrl"]
        self._send_command(
            websocket_url,
            "Page.navigate",
            {"url": AI_CHAT_URL},
        )
        deadline = time.monotonic() + DEBUGGER_TIMEOUT
        while time.monotonic() < deadline:
            page = self._evaluate(websocket_url, "({url:location.href,path:location.pathname})")
            if isinstance(page, dict) and str(page.get("path", "")).rstrip("/") == "/login":
                raise BrowserLaunchError(
                    "Chrome is open to Deepbrid login. Sign in, then send your message again."
                )
            if isinstance(page, dict) and str(page.get("path", "")).rstrip("/") == "/ai-chat":
                ready = self._evaluate(websocket_url, self._chat_ready_script())
                if isinstance(ready, dict) and ready.get("ready") is True:
                    return target
            time.sleep(0.25)
        raise BrowserLaunchError(
            "Could not open Deepbrid AI Chat. Check the browser and sign-in state, then retry."
        )

    def send_message(
        self,
        prompt: str,
        image_paths: list[Path] | None = None,
        project_root: Path | None = None,
        external_image_paths: list[Path] | None = None,
    ) -> str:
        if not prompt.strip():
            raise BrowserLaunchError("The prompt is empty; nothing was sent.")
        port = self._wait_for_debug_port()
        target = self._find_chat_target(port)
        if target is None:
            target = self._navigate_to_chat(port)
        websocket_url = target["webSocketDebuggerUrl"]
        chat_state = self._evaluate(websocket_url, self._chat_ready_script())
        if not isinstance(chat_state, dict) or chat_state.get("ready") is not True:
            error = chat_state.get("error") if isinstance(chat_state, dict) else None
            raise BrowserLaunchError(
                str(error)
                if isinstance(error, str)
                else "Sign in to Deepbrid AI Chat in the dedicated Chrome window, then retry."
            )
        images = image_paths or []
        try:
            external_images = {
                path.resolve(strict=True) for path in (external_image_paths or [])
            }
        except (OSError, RuntimeError) as error:
            raise BrowserLaunchError(f"Could not access a pasted image: {error}") from error
        if images and project_root is None and any(
            path.resolve(strict=True) not in external_images for path in images
        ):
            raise BrowserLaunchError(
                "Open a project folder before attaching selected images to Deepbrid AI Chat."
            )
        self._attach_images(websocket_url, images, project_root, external_images)
        state = self._evaluate(websocket_url, self._submit_script(prompt))
        if not isinstance(state, dict) or state.get("sent") is not True:
            error = state.get("error") if isinstance(state, dict) else None
            raise BrowserLaunchError(
                str(error) if isinstance(error, str) else "Could not submit the message in Deepbrid AI Chat."
            )
        assistant_count = state.get("assistantCount")
        if not isinstance(assistant_count, int):
            raise BrowserLaunchError("Deepbrid AI Chat did not confirm the submitted message.")
        self._wait_for_submission(websocket_url, assistant_count)

        deadline = time.monotonic() + RESPONSE_TIMEOUT
        while time.monotonic() < deadline:
            response_state = self._evaluate(websocket_url, self._response_state_script())
            if not isinstance(response_state, dict):
                raise BrowserLaunchError("Could not read the visible Deepbrid AI Chat response.")
            current_count = response_state.get("assistantCount")
            busy = response_state.get("busy")
            response = response_state.get("response")
            if (
                isinstance(current_count, int)
                and current_count > assistant_count
                and busy is False
                and isinstance(response, str)
                and response.strip()
            ):
                return response.strip()
            time.sleep(0.75)
        raise BrowserLaunchError(
            "The message was submitted, but Deepbrid AI Chat did not finish a response "
            f"within {RESPONSE_TIMEOUT} seconds. Check the browser and retry if needed."
        )

    def _wait_for_submission(self, websocket_url: str, assistant_count: int) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self._evaluate(
                websocket_url,
                self._submission_state_script(assistant_count),
            )
            if isinstance(state, dict) and state.get("accepted") is True:
                return
            time.sleep(0.2)
        raise BrowserLaunchError(
            "Deepbrid AI Chat did not accept the message. The prompt is still in the "
            "composer; check the attachment and try sending again."
        )

    def _wait_for_debug_port(self) -> int:
        deadline = time.monotonic() + DEBUGGER_TIMEOUT
        port_file = self.profile_dir / DEBUG_PORT_FILE
        if not port_file.exists() and self._process is None:
            raise BrowserLaunchError(
                'The dedicated Chrome browser is not open. Click "Open Deepbrid AI Chat" first.'
            )
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise BrowserLaunchError(
                    "The dedicated Chrome browser closed unexpectedly. Open it again and retry."
                )
            port = self._debug_port()
            if port is not None:
                return port
            time.sleep(0.1)
        raise BrowserLaunchError(
            "Could not connect to dedicated Chrome. Close any old Deepbrid Code Chrome window "
            "and reopen it from this app."
        )

    def _debug_port(self) -> int | None:
        try:
            port = int((self.profile_dir / DEBUG_PORT_FILE).read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None
        if not 1 <= port <= 65535:
            return None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
                version = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return None
        if not isinstance(version, dict):
            return None
        browser = version.get("Browser")
        return port if isinstance(browser, str) and browser.startswith("Chrome/") else None

    def _find_chat_target(self, port: int) -> dict[str, str] | None:
        return self._find_deepbrid_target(port, path="/ai-chat")

    def _find_deepbrid_target(
        self,
        port: int,
        path: str | None = None,
    ) -> dict[str, str] | None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as response:
                targets = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as error:
            raise BrowserLaunchError(f"Could not inspect the dedicated Chrome tabs: {error}") from error
        if not isinstance(targets, list):
            raise BrowserLaunchError("Chrome returned an invalid list of browser tabs.")
        for target in targets:
            if not isinstance(target, dict) or target.get("type") != "page":
                continue
            url = target.get("url")
            websocket_url = target.get("webSocketDebuggerUrl")
            if not isinstance(url, str) or not isinstance(websocket_url, str):
                continue
            try:
                parsed = urllib.parse.urlparse(url)
                debugger = urllib.parse.urlparse(websocket_url)
            except ValueError:
                continue
            if (
                parsed.scheme == "https"
                and parsed.hostname == "www.deepbrid.com"
                and (path is None or parsed.path.rstrip("/") == path)
                and debugger.scheme == "ws"
                and debugger.hostname in {"127.0.0.1", "localhost", "::1"}
                and debugger.port == port
            ):
                return {"webSocketDebuggerUrl": websocket_url}
        return None

    def _wait_for_deepbrid_target(
        self,
        port: int,
        path: str | None = None,
    ) -> dict[str, str] | None:
        deadline = time.monotonic() + DEBUGGER_TIMEOUT
        while time.monotonic() < deadline:
            target = self._find_deepbrid_target(port, path)
            if target is not None:
                return target
            time.sleep(0.2)
        return None

    def _attach_images(
        self,
        websocket_url: str,
        image_paths: list[Path],
        project_root: Path | None,
        external_image_paths: set[Path] | None = None,
    ) -> None:
        if not image_paths:
            return
        allowed_external_paths = external_image_paths or set()
        resolved_paths: list[Path] = []
        for path in image_paths:
            try:
                if path.is_symlink() or not path.is_file():
                    raise BrowserLaunchError(
                        f"Selected image is no longer a regular file: {path.name}"
                    )
                size = path.stat().st_size
                resolved_path = path.resolve(strict=True)
                if project_root is not None:
                    try:
                        resolved_path.relative_to(project_root.resolve(strict=True))
                    except ValueError:
                        if resolved_path not in allowed_external_paths:
                            raise
                elif resolved_path not in allowed_external_paths:
                    raise ValueError(
                        f"Selected image {path.name} is outside the opened project folder."
                    )
            except (OSError, RuntimeError) as error:
                raise BrowserLaunchError(
                    f"Could not access selected image {path.name}: {error}"
                ) from error
            except ValueError as error:
                raise BrowserLaunchError(
                    f"Selected image {path.name} is outside the opened project folder."
                ) from error
            if size > MAX_IMAGE_ATTACHMENT_BYTES:
                raise BrowserLaunchError(
                    f"{path.name} exceeds the {MAX_IMAGE_ATTACHMENT_BYTES // (1024 * 1024)} MiB image limit."
                )
            resolved_paths.append(resolved_path)
        initial_attachments = self._evaluate(
            websocket_url,
            self._attachment_state_script(),
        )
        if not isinstance(initial_attachments, dict):
            raise BrowserLaunchError("Could not inspect Deepbrid AI Chat attachments.")
        initial_names = initial_attachments.get("readyNames")
        if not isinstance(initial_names, list) or not all(
            isinstance(name, str) for name in initial_names
        ):
            raise BrowserLaunchError("Deepbrid AI Chat returned invalid attachment state.")
        initial_name_counts = Counter(initial_names)
        requested_name_counts = Counter(path.name for path in resolved_paths)
        expected_names = initial_name_counts.copy()
        for name, count in requested_name_counts.items():
            expected_names[name] = max(expected_names[name], count)
        connection = self._open_devtools_connection(websocket_url)
        try:
            document = self._send_command_on_connection(
                connection,
                "DOM.getDocument",
                {"depth": -1},
                command_id=1,
            )
            root = document.get("root")
            root_id = root.get("nodeId") if isinstance(root, dict) else None
            if not isinstance(root_id, int):
                raise BrowserLaunchError(
                    "Could not access the Deepbrid AI Chat attachment control."
                )
            query = self._send_command_on_connection(
                connection,
                "DOM.querySelector",
                {"nodeId": root_id, "selector": 'input[type="file"][accept*="image/"]'},
                command_id=2,
            )
            node_id = query.get("nodeId")
            if not isinstance(node_id, int) or node_id == 0:
                raise BrowserLaunchError(
                    "Deepbrid AI Chat no longer exposes its image attachment control. "
                    "Attach images manually in Chrome."
                )
            self._send_command_on_connection(
                connection,
                "DOM.setFileInputFiles",
                {
                    "nodeId": node_id,
                    "files": [str(path) for path in resolved_paths],
                },
                command_id=3,
            )
        finally:
            self._close_devtools_connection(connection)
        self._wait_for_image_attachments(websocket_url, expected_names)

    def _wait_for_image_attachments(
        self,
        websocket_url: str,
        expected_names: Counter[str],
    ) -> None:
        deadline = time.monotonic() + DEBUGGER_TIMEOUT
        expected_count = sum(expected_names.values())
        while time.monotonic() < deadline:
            state = self._evaluate(websocket_url, self._attachment_state_script())
            if not isinstance(state, dict):
                raise BrowserLaunchError("Could not confirm the image attachment state.")
            failed = state.get("failedNames")
            if isinstance(failed, list) and failed:
                raise BrowserLaunchError(
                    "Deepbrid AI Chat could not prepare these attachment(s): "
                    + ", ".join(str(name) for name in failed)
                )
            ready_names = state.get("readyNames")
            if not isinstance(ready_names, list) or not all(
                isinstance(name, str) for name in ready_names
            ):
                raise BrowserLaunchError("Deepbrid AI Chat returned invalid attachment state.")
            ready_counts = Counter(ready_names)
            if all(
                ready_counts[name] >= count
                for name, count in expected_names.items()
            ):
                return
            time.sleep(0.2)
        raise BrowserLaunchError(
            "Deepbrid AI Chat is still processing the image attachment. Wait for its "
            "thumbnail to finish loading, then retry."
        )

    @staticmethod
    def _attachment_state_script() -> str:
        return (
            "(()=>{const root=document.querySelector('.dfy-composer');"
            "if(!root)return {readyNames:[],failedNames:[]};"
            "return {readyNames:[...root.querySelectorAll('.dfy-att.is-ready .dfy-att-name')]"
            ".map(e=>(e.textContent||'').trim()).filter(Boolean),"
            "failedNames:[...root.querySelectorAll('.dfy-att.is-error,.dfy-att.is-failed')]"
            ".map(e=>e.querySelector('.dfy-att-name')?.textContent?.trim()||e.title||'image')};"
            "})()"
        )

    def _evaluate(self, websocket_url: str, expression: str) -> object:
        result = self._send_command(
            websocket_url,
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        remote = result.get("result") if isinstance(result, dict) else None
        if not isinstance(remote, dict):
            raise BrowserLaunchError("Chrome returned an invalid page evaluation result.")
        exception = result.get("exceptionDetails")
        if isinstance(exception, dict):
            details = exception.get("exception")
            description = details.get("description") if isinstance(details, dict) else None
            raise BrowserLaunchError(
                str(description or exception.get("text") or "Deepbrid AI Chat page error.")
            )
        return remote.get("value")

    @staticmethod
    def _send_command(websocket_url: str, method: str, params: dict[str, object]) -> dict[str, object]:
        connection = DeepbridChatBrowser._open_devtools_connection(websocket_url)
        try:
            return DeepbridChatBrowser._send_command_on_connection(
                connection,
                method,
                params,
                command_id=1,
            )
        finally:
            DeepbridChatBrowser._close_devtools_connection(connection)

    @staticmethod
    def _open_devtools_connection(websocket_url: str) -> websocket.WebSocket:
        parsed = urllib.parse.urlparse(websocket_url)
        if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise BrowserLaunchError("Refusing a non-local Chrome DevTools connection.")
        try:
            return websocket.create_connection(
                websocket_url,
                timeout=DEBUGGER_TIMEOUT,
                suppress_origin=True,
            )
        except (OSError, websocket.WebSocketException) as error:
            raise BrowserLaunchError(f"Could not connect to the dedicated Chrome page: {error}") from error

    @staticmethod
    def _send_command_on_connection(
        connection: websocket.WebSocket,
        method: str,
        params: dict[str, object],
        command_id: int,
    ) -> dict[str, object]:
        try:
            connection.send(json.dumps({"id": command_id, "method": method, "params": params}))
            deadline = time.monotonic() + DEBUGGER_TIMEOUT
            while time.monotonic() < deadline:
                message = json.loads(connection.recv())
                if not isinstance(message, dict) or message.get("id") != command_id:
                    continue
                if "error" in message:
                    detail = message["error"]
                    raise BrowserLaunchError(
                        f"Chrome DevTools {method} failed: {detail}"
                    )
                result = message.get("result")
                if isinstance(result, dict):
                    return result
                raise BrowserLaunchError(f"Chrome DevTools {method} returned an invalid result.")
            raise BrowserLaunchError(f"Chrome DevTools {method} timed out.")
        except (OSError, websocket.WebSocketException, json.JSONDecodeError) as error:
            raise BrowserLaunchError(f"Chrome DevTools {method} failed: {error}") from error

    @staticmethod
    def _close_devtools_connection(connection: websocket.WebSocket) -> None:
        try:
            connection.close()
        except (OSError, websocket.WebSocketException):
            pass

    @staticmethod
    def _submit_script(prompt: str) -> str:
        return (
            "(()=>{"
            "if(location.origin!=='https://www.deepbrid.com'||location.pathname!=='/ai-chat')"
            "return {error:'The active tab is not the Deepbrid AI Chat page.'};"
            "const input=document.querySelector('textarea[aria-label=\"Message\"]');"
            "const thread=document.querySelector('.dfy-thread');"
            "if(!input||!thread)return {error:'Sign in to Deepbrid AI Chat in the dedicated Chrome window, then retry.'};"
            "const button=input.parentElement?.querySelector('button.dfy-send');"
            "if(!button)return {error:'Could not find the visible chat send button.'};"
            "const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;"
            f"setter.call(input,{json.dumps(prompt)});"
            "input.dispatchEvent(new Event('input',{bubbles:true}));"
            "input.dispatchEvent(new Event('change',{bubbles:true}));"
            "if(button.disabled)return {error:'The chat is not ready to send. Check sign-in and attachments.'};"
            "const assistantCount=thread.querySelectorAll('.dfy-msg-asst').length;"
            "button.click();"
            "return {sent:true,assistantCount};"
            "})()"
        )

    @staticmethod
    def _chat_ready_script() -> str:
        return (
            "(()=>{"
            "if(location.origin!=='https://www.deepbrid.com'||location.pathname!=='/ai-chat')"
            "return {error:'The active tab is not the Deepbrid AI Chat page.'};"
            "const input=document.querySelector('textarea[aria-label=\"Message\"]');"
            "const thread=document.querySelector('.dfy-thread');"
            "return input&&thread?{ready:true}:"
            "{error:'Sign in to Deepbrid AI Chat in the dedicated Chrome window, then retry.'};"
            "})()"
        )

    @staticmethod
    def _response_state_script() -> str:
        return (
            "(()=>{"
            "const thread=document.querySelector('.dfy-thread');"
            "const messages=thread?[...thread.querySelectorAll('.dfy-msg-asst')]:[];"
            "const button=document.querySelector('textarea[aria-label=\"Message\"]')"
            "?.parentElement?.querySelector('button.dfy-send');"
            "const label=(button?.getAttribute('aria-label')||button?.title||'').trim();"
            "return {assistantCount:messages.length,"
            "busy:!!button&&!/^(send|envoyer)$/i.test(label),"
            "response:messages.at(-1)?.querySelector('.dfy-msg-content')?.innerText||''};"
            "})()"
        )

    @staticmethod
    def _submission_state_script(assistant_count: int) -> str:
        return (
            "(()=>{"
            "const input=document.querySelector('textarea[aria-label=\"Message\"]');"
            "const button=input?.parentElement?.querySelector('button.dfy-send');"
            "const label=(button?.getAttribute('aria-label')||button?.title||'').trim();"
            "const thread=document.querySelector('.dfy-thread');"
            "const currentCount=thread?.querySelectorAll('.dfy-msg-asst').length||0;"
            f"return {{accepted:!!input&&!!button&&(input.value.trim()===''||button.disabled||"
            f"(!/^(send|envoyer)$/i.test(label))||currentCount>{assistant_count})}};"
            "})()"
        )

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    @staticmethod
    def _find_chrome() -> str | None:
        configured = os.environ.get("DEEPBRID_CHROME_PATH")
        if configured and Path(configured).is_file():
            return configured
        found = shutil.which("chrome.exe" if sys.platform == "win32" else "google-chrome")
        if found:
            return found
        if sys.platform == "win32":
            roots = (
                Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
                Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
                Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")),
            )
            for root in roots:
                for relative in (
                    Path("Google") / "Chrome" / "Application" / "chrome.exe",
                    Path("Programs") / "Google" / "Chrome" / "Application" / "chrome.exe",
                ):
                    candidate = root / relative
                    if candidate.is_file():
                        return str(candidate)
        elif sys.platform == "darwin":
            candidate = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            if candidate.is_file():
                return str(candidate)
        return None
