"""Real Windows instance objects, portable logs and actual server lifecycle."""

import asyncio
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, Thread
import time
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from app.desktop import platform
from app.desktop.logging import SecretFilter, configure_logging
from app.desktop.server import DesktopServer


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named kernel objects")
def test_real_named_objects_activate_owner_and_release_without_pid_files(isolated_project):
    from app.desktop.instance import SingleInstance
    owner = SingleInstance(isolated_project)
    another_root = SingleInstance(isolated_project / "separate-copy")
    activated = Event()
    try:
        assert owner.owner and another_root.owner
        owner.watch(activated.set)
        script = ("from pathlib import Path; from app.desktop.instance import SingleInstance; "
                  "import json,sys; instance=SingleInstance(Path(sys.argv[1])); "
                  "print(json.dumps({'owner':instance.owner}),flush=True); instance.activate(); instance.close()")
        result = subprocess.run([sys.executable, "-c", script, str(isolated_project)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"owner": False}
        assert activated.wait(5)
    finally:
        owner.close()
        another_root.close()
    fresh = SingleInstance(isolated_project)
    try:
        assert fresh.owner
        assert not list(isolated_project.glob("*.pid"))
    finally:
        fresh.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named kernel objects")
def test_crashed_owner_does_not_leave_stale_ownership(isolated_project):
    from app.desktop.instance import SingleInstance
    script = ("from pathlib import Path; from app.desktop.instance import SingleInstance; "
              "import os,sys; instance=SingleInstance(Path(sys.argv[1])); print(instance.owner,flush=True); "
              "sys.stdin.readline(); os._exit(99)")
    child = subprocess.Popen([sys.executable, "-c", script, str(isolated_project)],
                             cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    duplicate = None
    try:
        assert child.stdout.readline().strip() == "True"
        duplicate = SingleInstance(isolated_project)
        assert not duplicate.owner
        # Windows venv python.exe can be a redirector; exit the interpreter itself.
        child.stdin.write("crash\n")
        child.stdin.flush()
        child.wait(timeout=10)
        assert child.returncode == 99
        fresh = SingleInstance(isolated_project)
        try:
            assert fresh.owner
        finally:
            fresh.close()
    finally:
        if duplicate is not None:
            duplicate.close()
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named kernel objects")
def test_same_process_duplicate_does_not_recursively_claim_or_release_owner(isolated_project):
    from app.desktop.instance import SingleInstance
    owner = SingleInstance(isolated_project)
    duplicate = SingleInstance(isolated_project)
    try:
        assert owner.owner and not duplicate.owner
        duplicate.close()
        still_duplicate = SingleInstance(isolated_project)
        try:
            assert not still_duplicate.owner
        finally:
            still_duplicate.close()
    finally:
        duplicate.close()
        owner.close()


def test_secret_filter_drops_raw_exception_and_preformatted_exception_text():
    secret = "model-key-private-sentinel"
    record = logging.LogRecord("app", logging.ERROR, __file__, 1, "Failed key %s", (secret,),
                               (ValueError, ValueError(secret), None))
    record.exc_text = "provider exception: " + secret
    SecretFilter([secret]).filter(record)
    output = logging.Formatter("%(message)s").format(record)
    assert secret not in output
    assert "[REDACTED]" in output and "ValueError" in output
    assert record.exc_info is None and record.exc_text is None
    record = logging.LogRecord("app", logging.ERROR, __file__, 1, "Already formatted", (), None)
    record.exc_text = secret
    SecretFilter().filter(record)
    assert secret not in logging.Formatter("%(message)s").format(record)


def test_logs_rotate_only_inside_portable_root_without_exception_secrets(isolated_project):
    root_logger = logging.getLogger()
    saved_handlers, saved_level = root_logger.handlers[:], root_logger.level
    names = ("uvicorn", "uvicorn.error", "uvicorn.access", "pywebview")
    saved_loggers = {name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
                     for name in names}
    created_handlers = []
    try:
        secret_filter = configure_logging(isolated_project)
        secret_filter.secrets = ("private-secret",)
        handler = root_logger.handlers[0]
        created_handlers = [handler]
        assert Path(handler.baseFilename) == isolated_project / "logs" / "memory-os.log"
        assert handler.maxBytes == 2 * 1024 * 1024 and handler.backupCount == 3
        handler.maxBytes = 180
        for _ in range(12):
            try:
                raise ValueError("private-secret")
            except ValueError:
                logging.getLogger("app.desktop.test").exception("private-secret startup failed")
        handler.flush()
        files = list((isolated_project / "logs").iterdir())
        assert 2 <= len(files) <= 4
        assert all(path.is_relative_to(isolated_project) for path in files)
        assert all("private-secret" not in path.read_text(encoding="utf-8") for path in files)
        assert all("Traceback" not in path.read_text(encoding="utf-8") for path in files)
    finally:
        root_logger.handlers = saved_handlers
        root_logger.setLevel(saved_level)
        for name, (handlers, propagate) in saved_loggers.items():
            logging.getLogger(name).handlers = handlers
            logging.getLogger(name).propagate = propagate
        for handler in created_handlers:
            handler.close()


class RegistryKey:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def install_registry(monkeypatch, *, webview="130.0.0.1", release=528040):
    def open_key(hive, path, *_):
        if "EdgeUpdate" in path and webview is None:
            raise FileNotFoundError()
        if "NET Framework" in path and release is None:
            raise FileNotFoundError()
        return RegistryKey(path)

    def query(key, name):
        return (webview if name == "pv" else release, 1)

    fake = SimpleNamespace(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2,
                           KEY_WOW64_32KEY=0x200, KEY_WOW64_64KEY=0x100,
                           KEY_READ=1, OpenKey=open_key, QueryValueEx=query)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(platform.sys, "platform", "win32")
    monkeypatch.setattr(platform.sys, "maxsize", 2**63 - 1)


@pytest.mark.parametrize("webview,release,error", [
    (None, 528040, "WebView2"),
    ("0.0.0.0", 528040, "WebView2"),
    ("invalid-version", 528040, "WebView2"),
    ("130.0.0.1", None, "NET"),
    ("130.0.0.1", 528039, "NET"),
    ("130.0.0.1", "not-a-number", "NET"),
])
def test_preflight_reports_missing_or_invalid_registry_data(monkeypatch, webview, release, error):
    install_registry(monkeypatch, webview=webview, release=release)
    with pytest.raises(platform.DesktopPlatformError, match=error):
        platform.prerequisites()


def test_preflight_accepts_supported_webview_and_dotnet(monkeypatch):
    install_registry(monkeypatch)
    platform.prerequisites()


@pytest.mark.parametrize("os_name,maxsize", [("linux", 2**63 - 1), ("win32", 2**31 - 1)])
def test_preflight_rejects_unsupported_os_and_32_bit(monkeypatch, os_name, maxsize):
    monkeypatch.setattr(platform.sys, "platform", os_name)
    monkeypatch.setattr(platform.sys, "maxsize", maxsize)
    with pytest.raises(platform.DesktopPlatformError, match="64"):
        platform.prerequisites()


def test_desktop_server_serves_actual_isolated_app_and_releases_port(settings):
    server = DesktopServer(settings)
    port = server.socket.getsockname()[1]
    try:
        assert server.socket.getsockname()[0] == "127.0.0.1"
        server.start()
        with httpx.Client(base_url=server.url, trust_env=False, timeout=10) as client:
            assert client.get("/health").json() == {"status": "ok", "database": "ok"}
            home = client.get("/")
            assert home.status_code == 200 and "text/html" in home.headers["content-type"]
            assert client.get("/api/v1/ui/overview").status_code == 200
            assert client.get("/api/v1/ui/knowledge").json()["total"] == 0
    finally:
        server.stop()
    assert not server.thread.is_alive()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_desktop_server_drains_inflight_request_before_lifespan_shutdown(settings, monkeypatch):
    from app import main as main_module
    from contextlib import asynccontextmanager
    started, release, shutdown, completed, index_stopped = Event(), Event(), Event(), Event(), Event()

    @asynccontextmanager
    async def lifespan(_):
        yield
        shutdown.set()

    app = FastAPI(lifespan=lifespan)
    app.state.rag_index = SimpleNamespace(request_stop=index_stopped.set)

    @app.get("/health")
    async def health():
        return {"status": "ok", "database": "ok"}

    @app.get("/slow")
    async def slow():
        started.set()
        await asyncio.to_thread(release.wait)
        completed.set()
        return {"completed": True}

    monkeypatch.setattr(main_module, "create_app", lambda _: app)
    server = DesktopServer(settings)
    replies, errors = [], []

    def request():
        try:
            replies.append(httpx.get(server.url + "/slow", timeout=10, trust_env=False))
        except Exception as error:
            errors.append(error)

    request_thread = Thread(target=request)
    stop_thread = Thread(target=server.stop)
    try:
        server.start()
        request_thread.start()
        assert started.wait(5)
        server.request_stop()
        assert index_stopped.is_set(), "New paid index batches must stop before HTTP requests finish."
        stop_thread.start()
        time.sleep(.25)
        assert stop_thread.is_alive() and not shutdown.is_set()
        release.set()
        request_thread.join(timeout=10)
        stop_thread.join(timeout=10)
        assert not errors
        assert replies[0].json() == {"completed": True}
        assert completed.is_set() and shutdown.is_set()
        assert not server.thread.is_alive() and not stop_thread.is_alive()
    finally:
        release.set()
        server.stop()
        if request_thread.ident:
            request_thread.join(timeout=10)
        if stop_thread.ident:
            stop_thread.join(timeout=10)
