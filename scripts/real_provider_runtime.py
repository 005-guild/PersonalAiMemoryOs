"""Own isolated local/Compose services without persisting provider credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from threading import Event, RLock, Thread
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_ROOT = PROJECT_ROOT / ".cache" / "real-provider-validation"
IMAGE = "personalaimemoryos-api:latest"
_ACTIVE: dict[Path, object] = {}
_ACTIVE_LOCK = RLock()
_PROXY_NAMES = {
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
}


class RuntimeFailure(RuntimeError):
    """A safe diagnostic containing neither subprocess output nor credentials."""


def _workspace(path: Path) -> Path:
    resolved = path.resolve()
    root = VALIDATION_ROOT.resolve()
    if not root.is_relative_to(PROJECT_ROOT.resolve()):
        raise RuntimeFailure("Validation root escaped the project.")
    if resolved == root or not resolved.is_relative_to(root):
        raise RuntimeFailure("Validation workspace must be beneath .cache/real-provider-validation.")
    return resolved


def _inside(path: Path, workspace: Path) -> Path:
    resolved = path.resolve()
    if resolved == workspace or not resolved.is_relative_to(workspace):
        raise RuntimeFailure("Validation path escaped its workspace.")
    return resolved


def _environment(values: dict[str, str]) -> dict[str, str]:
    # Do not inherit unrelated application configuration from the caller.
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("MEMORY_OS_")}
    environment.update(values)
    bypass = []
    for name in ("NO_PROXY", "no_proxy"):
        bypass.extend(part.strip() for part in environment.get(name, "").split(",") if part.strip())
    bypass.extend(("localhost", "127.0.0.1", "::1"))
    merged = ",".join(dict.fromkeys(bypass))
    environment.update(NO_PROXY=merged, no_proxy=merged, PYTHONDONTWRITEBYTECODE="1")
    return environment


def create_isolated_app():
    """Uvicorn factory which never falls back to the personal project .env."""
    from app.config import Settings
    from app.main import create_app

    return create_app(Settings(_env_file=None))


def run_isolated(port: int, stop_path: str) -> None:
    """Run hidden on Windows, using a local sentinel for graceful Uvicorn shutdown."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(
        create_isolated_app(), host="127.0.0.1", port=port, workers=1,
        log_level="warning", access_log=False,
    ))
    finished = Event()

    def request_stop() -> None:
        while not finished.wait(0.2):
            if Path(stop_path).exists():
                server.should_exit = True
                return

    watcher = Thread(target=request_stop, name="acceptance-stop", daemon=True)
    watcher.start()
    try:
        server.run()
    finally:
        finished.set()
        watcher.join(timeout=1)


class _Runtime:
    def __init__(self, workspace: Path, profile_file: Path, environment: dict[str, str]) -> None:
        self.workspace = _workspace(workspace)
        self.database = _inside(self.workspace / "data" / "memory.db", self.workspace)
        self.vault = _inside(self.workspace / "knowledge", self.workspace)
        self.profile_file = _inside(profile_file, self.workspace)
        if not self.profile_file.is_file():
            raise RuntimeFailure("The isolated provider profile file is missing.")
        self._environment = _environment(environment)
        self.base_url = ""
        self._claimed = False

    def _prepare(self) -> None:
        _workspace(self.workspace)
        for path in (self.database, self.vault, self.profile_file):
            _inside(path, self.workspace)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.vault.mkdir(parents=True, exist_ok=True)

    def _claim(self) -> None:
        with _ACTIVE_LOCK:
            if self.workspace in _ACTIVE:
                raise RuntimeFailure("Stop the existing validation service before sharing its storage.")
            _ACTIVE[self.workspace] = self
            self._claimed = True

    def _release(self) -> None:
        with _ACTIVE_LOCK:
            if _ACTIVE.get(self.workspace) is self:
                del _ACTIVE[self.workspace]
            self._claimed = False

    def _ready(self, *, exited=None, timeout: float = 50) -> None:
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if exited is not None and exited():
                raise RuntimeFailure("The isolated service exited during startup.")
            try:
                with opener.open(self.base_url + "/health", timeout=2) as response:
                    if response.status == 200 and json.loads(response.read(65_536)) == {
                        "status": "ok", "database": "ok",
                    }:
                        return
            except (OSError, HTTPError, URLError, ValueError):
                pass
            time.sleep(0.25)
        raise RuntimeFailure("The isolated service health check timed out.")


class LocalRuntime(_Runtime):
    """One hidden Uvicorn process with explicitly isolated SQLite and Markdown."""

    def __init__(self, workspace: Path, profile_file: Path, environment: dict[str, str]) -> None:
        super().__init__(workspace, profile_file, environment)
        self.process: subprocess.Popen | None = None
        self._stop_path = self.workspace / ".local-stop"

    def environment(self) -> dict[str, str]:
        return {
            **self._environment,
            "MEMORY_OS_DATABASE_URL": f"sqlite:///{self.database.as_posix()}",
            "MEMORY_OS_KNOWLEDGE_DIR": str(self.vault),
            "MEMORY_OS_AI_CONFIG_FILE": str(self.profile_file),
            "MEMORY_OS_SYNC_ENABLED": "true",
            "MEMORY_OS_SYNC_INTERVAL": "2",
            "MEMORY_OS_DELETION_GRACE": "10",
            "MEMORY_OS_LOG_LEVEL": "WARNING",
        }

    def migrate(self) -> None:
        with _ACTIVE_LOCK:
            if self.workspace in _ACTIVE:
                raise RuntimeFailure("Stop validation services before running explicit migration.")
            self._prepare()
            # Inject a connection, so migrations/env.py does not load Settings/.env.
            code = (
                "import os; from alembic import command; from alembic.config import Config; "
                "from app.repositories.database import Database; "
                "db=Database(os.environ['MEMORY_OS_DATABASE_URL']); db.initialize(); "
                "connection=db.engine.connect(); cfg=Config('alembic.ini'); "
                "cfg.attributes['connection']=connection; command.upgrade(cfg,'head'); "
                "connection.close(); db.dispose()"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=self.environment(),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RuntimeFailure(f"Isolated migration failed ({type(error).__name__}).") from None
            if result.returncode:
                raise RuntimeFailure(f"Isolated migration failed (exit {result.returncode}).")

    def start(self) -> None:
        self._claim()
        try:
            self._prepare()
            _inside(self._stop_path, self.workspace)
            self._stop_path.unlink(missing_ok=True)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            self.base_url = f"http://127.0.0.1:{port}"
            code = (
                "import sys; from scripts.real_provider_runtime import run_isolated; "
                "run_isolated(int(sys.argv[1]),sys.argv[2])"
            )
            self.process = subprocess.Popen(
                [sys.executable, "-c", code, str(port), str(self._stop_path)],
                cwd=PROJECT_ROOT, env=self.environment(), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._ready(exited=lambda: self.process.poll() is not None)
        except Exception as error:
            if self.process is not None:
                self.stop()
            else:
                self._release()
            if isinstance(error, RuntimeFailure):
                raise
            raise RuntimeFailure(f"Local startup failed ({type(error).__name__}).") from None

    def stop(self) -> None:
        if self.process is None:
            self._release()
            return
        if self.process.poll() is None:
            _inside(self._stop_path, self.workspace).write_text("stop\n", encoding="ascii")
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                raise RuntimeFailure("Local shutdown timed out; the process was not force-killed.") from None
        self.process = None
        self._release()


class DockerRuntime(_Runtime):
    """An exclusively owned Compose project; image builds and pulls are forbidden."""

    def __init__(self, workspace: Path, profile_file: Path, environment: dict[str, str]) -> None:
        super().__init__(workspace, profile_file, environment)
        self.project = "memory-os-real-" + uuid4().hex[:12]
        self._manifest = self.workspace / f"{self.project}.compose.json"
        self._empty_env = self.workspace / f"{self.project}.empty.env"
        self._started = False

    def environment(self) -> dict[str, str]:
        return {
            **self._environment,
            "MEMORY_OS_DATABASE_URL": "sqlite:////app/data/memory.db",
            "MEMORY_OS_KNOWLEDGE_DIR": "/app/knowledge",
            "MEMORY_OS_AI_CONFIG_FILE": "/app/config/ai-providers.yml",
            "MEMORY_OS_SYNC_ENABLED": "true",
            "MEMORY_OS_SYNC_INTERVAL": "2",
            "MEMORY_OS_DELETION_GRACE": "10",
            "MEMORY_OS_LOG_LEVEL": "WARNING",
        }

    def _compose(self, *arguments: str, timeout: float = 60) -> str:
        command = [
            "docker", "compose", "--project-name", self.project,
            "--env-file", str(self._empty_env), "--file", str(self._manifest), *arguments,
        ]
        try:
            result = subprocess.run(
                command, cwd=self.workspace, env=self.environment(), capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeFailure(f"Isolated Compose failed ({type(error).__name__}).") from None
        if result.returncode:
            raise RuntimeFailure(f"Isolated Compose failed (exit {result.returncode}).")
        return result.stdout

    def _write_manifest(self) -> None:
        names = sorted(name for name in self.environment()
                       if name.startswith("MEMORY_OS_") or name in _PROXY_NAMES)
        manifest = {"services": {"api": {
            "image": IMAGE, "pull_policy": "never", "environment": names,
            "ports": [{"target": 8000, "published": "0", "host_ip": "127.0.0.1"}],
            "volumes": [
                {"type": "bind", "source": str(self.database.parent), "target": "/app/data"},
                {"type": "bind", "source": str(self.vault), "target": "/app/knowledge"},
                {"type": "bind", "source": str(self.profile_file),
                 "target": "/app/config/ai-providers.yml", "read_only": True},
            ],
        }}}
        _inside(self._manifest, self.workspace).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _inside(self._empty_env, self.workspace).write_text("", encoding="ascii")

    def start(self) -> None:
        self._claim()
        try:
            self._prepare()
            self._write_manifest()
            # Set before dispatch: even an interrupted `up` can have created resources.
            self._started = True
            self._compose("up", "-d", "--no-build", "--pull", "never", "api")
            output = self._compose("port", "api", "8000").strip()
            match = re.fullmatch(r"127\.0\.0\.1:(\d{1,5})", output)
            if match is None or not 1 <= int(match[1]) <= 65535:
                raise RuntimeFailure("Compose did not publish an exclusive loopback port.")
            self.base_url = "http://" + output
            self._ready()
        except Exception as error:
            if self._started:
                self.stop()
            else:
                self._release()
            if isinstance(error, RuntimeFailure):
                raise
            raise RuntimeFailure(f"Isolated Compose startup failed ({type(error).__name__}).") from None

    def stop(self) -> None:
        if self._started:
            self._compose("down", "--timeout", "30", timeout=50)
            self._started = False
        self._release()
