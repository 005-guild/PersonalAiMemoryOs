"""Project-local process and HTTP helpers for isolated release acceptance."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import tomllib
from typing import Callable, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_VERSION = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
T = TypeVar("T")


def isolated_proxy_environment() -> dict[str, str]:
    """Child services must never send synthetic traffic through user proxies."""
    return {
        "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
        "http_proxy": "", "https_proxy": "", "all_proxy": "",
        "NO_PROXY": "localhost,127.0.0.1,::1,mock_model",
        "no_proxy": "localhost,127.0.0.1,::1,mock_model",
    }


def eventually(check: Callable[[], T], *, timeout: float = 40) -> T:
    """Wait for a true result, preserving transient errors for useful failures."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (AssertionError, OSError, HTTPError, URLError) as error:
            last_error = error
        time.sleep(0.25)
    raise AssertionError(f"Timed out waiting for verification condition: {last_error}")


def note_path(vault: Path, note_id: str) -> Path | None:
    for candidate in vault.rglob("*.md"):
        parts = candidate.read_text(encoding="utf-8").split("---", 2)
        if len(parts) != 3:
            continue
        header = yaml.safe_load(parts[1])
        if isinstance(header, dict) and str(header.get("id")) == note_id:
            return candidate
    return None


class RunningMockModel:
    """Own a synthetic model service without depending on real provider credentials."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.process: subprocess.Popen | None = None
        self.log_file = None
        self.port = 0

    def start(self) -> str:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.log_file = (self.workspace / "mock-model.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "scripts/mock_model_server.py"), "--port", str(self.port),
             "--records", str(self.workspace / "mock-requests.jsonl")],
            cwd=PROJECT_ROOT, stdout=self.log_file, stderr=subprocess.STDOUT,
            env={**os.environ, **isolated_proxy_environment()},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        base_url = f"http://127.0.0.1:{self.port}"

        def ready():
            if self.process.poll() is not None:
                raise RuntimeError("The isolated mock model process stopped during startup")
            with build_opener(ProxyHandler({})).open(base_url + "/health", timeout=3) as response:
                return response.status == 200

        eventually(ready)
        return base_url

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None


class RunningApp:
    """Own one isolated real Uvicorn process and its SQLite/Markdown storage."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.database = workspace / "data" / "memory.db"
        self.vault = workspace / "knowledge"
        self.log_path = workspace / "server.log"
        self.process: subprocess.Popen | None = None
        self.log_file = None
        self.port = 0
        self.ai_environment: dict[str, str] = {}

    def environment(self, *, sync_enabled: bool = True) -> dict[str, str]:
        return {
            **os.environ,
            "MEMORY_OS_DATABASE_URL": f"sqlite:///{self.database.as_posix()}",
            "MEMORY_OS_KNOWLEDGE_DIR": str(self.vault),
            "MEMORY_OS_SYNC_ENABLED": str(sync_enabled).lower(),
            "MEMORY_OS_SYNC_INTERVAL": "2",
            "MEMORY_OS_DELETION_GRACE": "10",
            "MEMORY_OS_LOG_LEVEL": "INFO",
            "MEMORY_OS_AI_ENABLED": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            **self.ai_environment,
            **isolated_proxy_environment(),
        }

    def migrate(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            raise RuntimeError(f"Explicit migration failed:\n{result.stdout}\n{result.stderr}")

    def start(self, *, sync_enabled: bool = True) -> None:
        if self.process is not None:
            raise RuntimeError("Stop the current process before restarting it.")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.log_file = self.log_path.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
                "--host", "127.0.0.1", "--port", str(self.port), "--workers", "1",
            ],
            cwd=PROJECT_ROOT,
            env=self.environment(sync_enabled=sync_enabled),
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )

        def ready() -> bool:
            if self.process.poll() is not None:
                raise RuntimeError(f"Uvicorn exited during startup:\n{self.logs()}")
            return self.api("GET", "/health") == {"status": "ok", "database": "ok"}

        eventually(ready)

    def api(self, method: str, path: str, body: dict | None = None):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with build_opener(ProxyHandler({})).open(request, timeout=100) as response:
            content = response.read()
            return json.loads(content) if content else None

    def note(self, note_id: str, *, include_deleted: bool = False) -> dict:
        suffix = "?include_deleted=true" if include_deleted else ""
        return self.api("GET", f"/api/v1/knowledge/{note_id}{suffix}")

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
            if self.log_file:
                self.log_file.close()
                self.log_file = None

    def logs(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace") if self.log_path.exists() else ""
