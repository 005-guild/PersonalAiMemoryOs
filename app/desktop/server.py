"""Own one loopback socket and one gracefully drained Uvicorn thread."""

import json
import logging
from pathlib import Path
import socket
import secrets
from threading import Thread
import time
from urllib.request import ProxyHandler, build_opener

import uvicorn

logger = logging.getLogger(__name__)


def loopback_socket():
    """Reserve a dynamic high port, avoiding Chromium's blocked service ports.

    https://raw.githubusercontent.com/chromium/chromium/main/net/base/port_util.cc
    Windows may assign 6668 to bind(0); never relax browser port restrictions.
    """
    for _ in range(64):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", 49152 + secrets.randbelow(16384)))
            return listener
        except OSError:
            listener.close()
    raise RuntimeError("无法预留本机桌面端口，请关闭多余实例后重试。")


class DesktopServer:
    def __init__(self, settings):
        from app.main import create_app
        self.socket = loopback_socket()
        self.url = "http://127.0.0.1:" + str(self.socket.getsockname()[1])
        try:
            app = create_app(settings)
            self.app = app
            config = uvicorn.Config(app, host="127.0.0.1", loop="asyncio", http="h11", ws="none",
                lifespan="on", log_config=None, access_log=False, timeout_graceful_shutdown=None)
            self.server = uvicorn.Server(config)
            self.thread = Thread(target=self._run, name="desktop-api", daemon=False)
        except BaseException:
            self.socket.close()
            raise

    def _run(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as error:
            logger.error("Desktop API stopped (%s).", type(error).__name__)

    def start(self):
        self.thread.start()
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic()+45
        while self.thread.is_alive() and time.monotonic()<deadline:
            if self.server.started:
                try:
                    with opener.open(self.url+"/health", timeout=1) as response:
                        if json.load(response) == {"status":"ok", "database":"ok"}:
                            return
                except (OSError, ValueError):
                    pass
            time.sleep(.05)
        self.stop()
        raise RuntimeError("本地服务启动失败，请查看 logs/memory-os.log。")

    def stop(self):
        self.request_stop()
        if self.thread.ident:
            self.thread.join()
        self.socket.close()

    def request_stop(self):
        # This public method only flips an intent flag; no asyncio primitive is
        # touched from the UI thread. Stop new paid batches before HTTP drain,
        # rather than waiting until lifespan shutdown after long text requests.
        if hasattr(self.app.state, "rag_index"):
            self.app.state.rag_index.request_stop()
        if hasattr(self.app.state, "processing"):
            self.app.state.processing.request_stop()
        if hasattr(self.app.state, "zhihu_sync"):
            self.app.state.zhihu_sync.request_stop()
        self.server.should_exit = True
