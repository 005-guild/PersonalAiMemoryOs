"""Restart only this portable executable after its original process fully exits."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock
import time
from uuid import uuid4

from app.paths import portable_path

WAIT_FLAG = "--desktop-restart-wait"


def wait_for_restart(root: Path, arguments: list[str]) -> bool:
    """A fresh executable waits on the exact parent handle before taking its mutex."""
    if len(arguments) != 3 or arguments[0] != WAIT_FLAG:
        raise ValueError("Invalid restart request.")
    parent = int(arguments[1])
    token = arguments[2]
    if parent <= 0 or parent == os.getpid() or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid restart request.")
    ready = portable_path(root, root / ".cache/desktop" / f"restart-{token}.ready")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE; never terminate.
    if not handle:
        raise OSError("Cannot inspect the original application process.")
    try:
        ready.parent.mkdir(parents=True, exist_ok=True)
        with ready.open("x", encoding="ascii") as stream:
            stream.write(token)
        if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) != 0:
            raise OSError("Cannot wait for the original application process.")
    finally:
        kernel.CloseHandle(handle)
        ready.unlink(missing_ok=True)
    return True


class DesktopRestarter:
    def __init__(self, root: Path, controller, *, executable=None, spawn=None):
        self.root, self.controller = root, controller
        self.executable = str(executable or sys.executable)
        self.spawn = spawn or subprocess.Popen
        self.pending = False
        self.lock = Lock()

    def request(self) -> bool:
        with self.lock:
            if self.pending:
                return False
            self.pending = True
        if not self.controller.request_restart(self):
            self.cancel()
            return False
        return True

    def cancel(self):
        with self.lock:
            self.pending = False

    def prepare(self):
        """Ensure the successor can start before shutting down the current window."""
        token = uuid4().hex
        ready = portable_path(self.root, self.root / ".cache/desktop" / f"restart-{token}.ready")
        command = [self.executable, WAIT_FLAG, str(os.getpid()), token]
        child = self.spawn(command, cwd=str(self.root), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError("Restart helper could not start.")
                if ready.is_file() and ready.read_text(encoding="ascii") == token:
                    return
                time.sleep(.05)
            raise RuntimeError("Restart helper did not become ready.")
        except Exception:
            # This helper has not owned an application or made any model call.
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
            ready.unlink(missing_ok=True)
            self.cancel()
            raise
