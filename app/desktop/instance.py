"""Per-portable-directory named kernel objects; no stale PID-file ownership."""

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
from threading import Event, Lock, Thread

_OWNED_ROOTS: set[str] = set()
_OWNERS_LOCK = Lock()


class SingleInstance:
    def __init__(self, root: Path):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        for name in ("ReleaseMutex", "SetEvent", "CloseHandle"):
            function = getattr(self.kernel, name)
            function.argtypes = [wintypes.HANDLE]
            function.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        identity = hashlib.sha256(os.path.normcase(str(root.resolve())).encode("utf-8")).hexdigest()
        self.identity = identity
        self.owner = False
        self.mutex = self.kernel.CreateMutexW(None, False, "Local\\MemoryOS-" + identity)
        if not self.mutex:
            raise OSError("Cannot acquire application instance mutex.")
        # Existence alone is insufficient after a crash: claim abandoned mutexes.
        # The local guard also avoids recursive ownership on the same UI thread.
        with _OWNERS_LOCK:
            if identity not in _OWNED_ROOTS:
                result = self.kernel.WaitForSingleObject(self.mutex, 0)
                if result in (0, 128):  # WAIT_OBJECT_0 / WAIT_ABANDONED
                    self.owner = True
                    _OWNED_ROOTS.add(identity)
                elif result != 258:  # WAIT_TIMEOUT: an active other process owns it.
                    self.kernel.CloseHandle(self.mutex)
                    self.mutex = None
                    raise OSError("Cannot inspect application instance mutex.")
        self.event = self.kernel.CreateEventW(None, False, False, "Local\\MemoryOS-activate-" + identity)
        if not self.event:
            self.close()
            raise OSError("Cannot create application activation event.")
        self.stop = Event()
        self.thread = None

    def activate(self) -> None:
        self.kernel.SetEvent(self.event)

    def watch(self, callback) -> None:
        def run():
            while not self.stop.is_set():
                if self.kernel.WaitForSingleObject(self.event, 500) == 0 and not self.stop.is_set():
                    callback()
        self.thread = Thread(target=run, name="desktop-activation", daemon=True)
        self.thread.start()

    def close(self) -> None:
        if hasattr(self, "stop"):
            self.stop.set()
        if getattr(self, "event", None):
            self.kernel.SetEvent(self.event)
        if getattr(self, "thread", None):
            self.thread.join(timeout=2)
        if getattr(self, "event", None):
            self.kernel.CloseHandle(self.event)
            self.event = None
        if getattr(self, "mutex", None):
            if self.owner:
                self.kernel.ReleaseMutex(self.mutex)
                with _OWNERS_LOCK:
                    _OWNED_ROOTS.discard(self.identity)
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None
