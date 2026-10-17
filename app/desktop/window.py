"""Asynchronous native close protection and drained backend shutdown."""

import json
import logging
import os
from pathlib import Path
from threading import Lock, Thread
import time

from app.desktop.platform import TITLE, message
from app.paths import portable_path

logger = logging.getLogger(__name__)


class DesktopWindow:
    def __init__(self, root: Path, backend):
        self.root, self.backend = root, backend
        self.window = None
        self.allow_close = False
        self.lock = Lock()
        self.asking = False
        self.stopping = False
        self.state_path = portable_path(root, root / ".cache/desktop/runtime.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def state(self, status):
        try:
            temporary = self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"pid": os.getpid(), "url": self.backend.url,
                "status": status, "window_title": TITLE}, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.state_path)
        except OSError as error:
            # Diagnostic metadata must never prevent draining or application exit.
            logger.warning("Desktop status update failed (%s).", type(error).__name__)

    def closing(self):
        # This handler is on the WinForms thread: do not wait for JavaScript here.
        if self.allow_close:
            return True
        with self.lock:
            if not self.asking and not self.stopping:
                self.asking = True
                Thread(target=self._ask, name="desktop-close-confirmation", daemon=True).start()
        return False

    def request_restart(self, restarter):
        with self.lock:
            if self.asking or self.stopping:
                return False
            self.asking = True
        Thread(target=self._ask, kwargs={"restarter": restarter}, name="desktop-restart-confirmation", daemon=True).start()
        return True

    def _ask(self, restarter=None):
        allowed = False
        try:
            ready = self.window.run_js("typeof window.memoryOsHasUnsavedChanges === 'function'")
            if ready is not True:
                allowed = message("工作台尚未加载完成。确定退出应用？", question=True)
            else:
                self.window.run_js("window.memoryOsDesktopCloseResult = null; window.dispatchEvent(new Event('memory-os-desktop-request-close')); null;")
                requested = time.monotonic()
                while self.window is not None and not self.allow_close:
                    result = self.window.run_js("window.memoryOsDesktopCloseResult")
                    if isinstance(result, bool):
                        allowed = result
                        break
                    if time.monotonic()-requested>1 and self.window.run_js("window.memoryOsDesktopClosePending === true") is not True:
                        allowed = message("页面正在切换或无法读取编辑状态，未保存的修改可能丢失。确定退出应用？", question=True)
                        break
                    time.sleep(.1)
        except Exception as error:
            logger.error("Desktop close confirmation failed (%s).", type(error).__name__)
            allowed = message("无法读取页面状态，未保存的修改可能丢失。确定退出应用？", question=True)
        finally:
            with self.lock:
                if not (allowed and restarter is not None):
                    self.asking = False
        if allowed:
            if restarter is not None:
                try:
                    restarter.prepare()
                except Exception as error:
                    logger.error("Desktop restart preparation failed (%s).", type(error).__name__)
                    restarter.cancel()
                    with self.lock:
                        self.asking = False
                    message("重启准备失败，当前应用仍保持运行。请查看日志后手动退出重开。")
                    return
            self.shutdown()
        elif restarter is not None:
            restarter.cancel()

    def shutdown(self):
        with self.lock:
            if self.stopping:
                return
            self.stopping = True
        self.state("stopping")
        try:
            self.window.run_js("window.dispatchEvent(new Event('memory-os-desktop-stopping')); null;")
        except Exception:
            pass
        self.backend.request_stop()
        deadline = time.monotonic()+150
        warned = False
        while self.backend.thread.is_alive():
            self.backend.thread.join(timeout=.25)
            if not warned and time.monotonic()>deadline:
                warned = True
                logger.warning("Waiting for in-flight requests to finish; no forced shutdown.")
                try:
                    self.window.run_js("window.dispatchEvent(new Event('memory-os-desktop-long-shutdown')); null;")
                except Exception:
                    pass
        self.state("stopped")
        self.allow_close = True
        self.window.destroy()

    def activate(self):
        try:
            if self.window is not None and not self.allow_close:
                self.window.restore()
                self.window.show()
        except Exception as error:
            logger.warning("Desktop activation failed (%s).", type(error).__name__)
