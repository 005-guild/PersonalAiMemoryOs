"""Own an isolated frozen desktop process and inspect its real WebView2 window."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from urllib.request import ProxyHandler, Request, build_opener

from verification_support import eventually, isolated_proxy_environment


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class FrozenDesktop:
    """No system Python, uv or Docker is on the child application's PATH."""

    def __init__(self, root: Path, evidence: Path):
        self.root, self.evidence = root, evidence
        self.process: subprocess.Popen | None = None
        self.port = free_port()
        self.url = ""
        self.runtime: dict = {}
        self.log_file = None
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("MEMORY_OS_", "PYTHON", "UV_", "WEBVIEW2_"))
        }
        self.environment.update({
            **isolated_proxy_environment(),
            "PATH": str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"),
            "MEMORY_OS_DESKTOP_TEST_MODE": "1",
            "MEMORY_OS_DESKTOP_DEBUG_PORT": str(self.port),
            "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": (
                f"--remote-debugging-port={self.port} --remote-debugging-address=127.0.0.1"
            ),
        })
        temporary = self.root / ".cache/verification-tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        self.environment.update({name: str(temporary) for name in ("TEMP", "TMP", "TMPDIR")})

    def start(self):
        runtime = self.root / ".cache/desktop/runtime.json"
        self.log_file = (self.evidence / "launch-output.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(self.root / "PersonalAiMemoryOs.exe")], cwd=self.evidence,
            env=self.environment, stdout=self.log_file, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        def ready():
            if self.process.poll() is not None:
                raise RuntimeError(f"Frozen desktop exited during startup ({self.process.returncode})")
            if not runtime.exists():
                return False
            state = json.loads(runtime.read_text(encoding="utf-8"))
            if state.get("pid") != self.process.pid:
                return False
            self.runtime = state
            self.url = state.get("url", state.get("base_url", "")).rstrip("/")
            return self.url and self.request("GET", "/health") == {"status": "ok", "database": "ok"}

        eventually(ready, timeout=100)
        return self

    def request(self, method, path, body=None):
        request = Request(self.url + path,
                          data=None if body is None else json.dumps(body).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method=method)
        with build_opener(ProxyHandler({})).open(request, timeout=100) as response:
            data = response.read()
            return json.loads(data) if data else None

    def cdp_ready(self):
        try:
            with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{self.port}/json/version", timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    def window(self):
        """Locate a visible top-level HWND belonging only to the owned EXE."""
        assert self.process is not None
        handles = []
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL

        @callback_type
        def visit(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.process.pid and user32.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True

        user32.EnumWindows(visit, 0)
        return handles[0] if handles else None

    def request_close(self):
        hwnd = eventually(self.window, timeout=10)
        post = ctypes.windll.user32.PostMessageW
        post.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        assert post(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def dialog_text(self):
        hwnd = self.window()
        if not hwnd:
            return None
        user32 = ctypes.windll.user32
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        labels = []
        buttons = []
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

        def label(handle):
            buffer = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(handle) + 1)
            user32.GetWindowTextW(handle, buffer, len(buffer))
            if buffer.value:
                labels.append(buffer.value)

        label(hwnd)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
        user32.EnumChildWindows.restype = wintypes.BOOL

        @callback_type
        def visit(child, _):
            label(child)
            class_name = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(child, class_name, len(class_name))
            if class_name.value == "Button":
                buttons.append(child)
            return True

        user32.EnumChildWindows(hwnd, visit, 0)
        return {"hwnd": hwnd, "text": "\n".join(labels), "buttons": buttons}

    def wait_closed(self, timeout=40):
        assert self.process is not None
        self.process.wait(timeout=timeout)
        assert self.process.returncode == 0, f"Desktop exit: {self.process.returncode}"
        old_url = self.url
        eventually(lambda: self._port_closed(old_url), timeout=10)
        self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    @staticmethod
    def _port_closed(url):
        from urllib.parse import urlsplit
        address = urlsplit(url)
        with socket.socket() as client:
            client.settimeout(0.3)
            return client.connect_ex(("127.0.0.1", address.port)) != 0

    def stop(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                self.request_close()
                self.wait_closed(timeout=20)
                return
            except (AssertionError, OSError, subprocess.TimeoutExpired):
                # Failure cleanup targets only this verifier's known owned process.
                self.process.kill()
                self.process.wait(timeout=10)
        self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None


def attach_window(playwright, app):
    eventually(app.cdp_ready, timeout=80)
    browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{app.port}")
    context = browser.contexts[0]
    # Playwright synchronous events must be pumped by its own waits. Sleeping in
    # a Python loop leaves an initially about:blank page's URL permanently stale.
    page = context.pages[0] if context.pages else context.wait_for_event("page", timeout=45000)
    page.wait_for_url(re.compile(re.escape(app.url) + r"(?:/|$)"), timeout=45000)
    page.locator("#page-title").wait_for()
    return browser, page


def check_invalid_configuration(root: Path, evidence: Path):
    """Inspect and dismiss the real startup error dialog on this isolated copy."""
    application = FrozenDesktop(root, evidence)
    environment_file = root / ".env"
    original = environment_file.read_bytes()
    try:
        environment_file.write_text("MEMORY_OS_DATABASE_URL=sqlite:///../outside.db\n", encoding="utf-8")
        application.process = subprocess.Popen([str(root / "PersonalAiMemoryOs.exe")], cwd=evidence,
                                             env=application.environment,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
        dialog = eventually(application.dialog_text, timeout=30)
        assert "Personal AI Memory OS" in dialog["text"]
        assert any(word in dialog["text"] for word in ("目录", "配置", "路径")), dialog["text"]
        (evidence / "configuration-error-dialog.json").write_text(json.dumps(dialog, ensure_ascii=False, indent=2), encoding="utf-8")
        post = ctypes.windll.user32.PostMessageW
        post.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        assert dialog["buttons"], "The startup error has no native acknowledgement button"
        assert post(dialog["buttons"][0], 0x00F5, 0, 0)  # BM_CLICK on the real native button
        assert application.process.wait(timeout=15) != 0
        application.process = None
        assert not (root.parent / "outside.db").exists()
        return {"status": "passed", "dialog": dialog["text"], "out_of_root_file_created": False}
    finally:
        application.stop()
        environment_file.write_bytes(original)
