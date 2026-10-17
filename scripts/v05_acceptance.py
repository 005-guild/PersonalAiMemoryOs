"""Verify v0.5 with real isolated Qdrant, offline models, and project-local data."""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from uuid import uuid4
from urllib.request import ProxyHandler, build_opener

import yaml

from verification_support import PROJECT_ROOT, RunningApp, eventually, isolated_proxy_environment
from v05_workflow import API, check_restart, run_workflow

QDRANT_IMAGE = "qdrant/qdrant:v1.19.2"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def json_file(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def storage_fingerprint() -> dict:
    files = [PROJECT_ROOT / "data/memory.db", *(PROJECT_ROOT / "knowledge").rglob("*")]
    return {str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file()}


def profiles(workspace: Path, model_url: str) -> tuple[Path, Path]:
    directory = workspace / "config"
    directory.mkdir(exist_ok=True)
    shared = {"enabled": True, "base_url": model_url, "api_key_ref": "verification", "auth": "bearer"}
    ai = {"schema_version": 1, "default_profile": "offline", "profiles": {"offline": {
        **shared, "protocol": "openai_chat", "model": "v05-offline-chat", "response_format": "json_object",
        "max_output_tokens": 2048, "timeout_seconds": 30,
    }}}
    embedding = {"schema_version": 1, "default_profile": "offline", "profiles": {"offline": {
        **shared, "protocol": "openai_embeddings", "model": "v05-offline-embedding",
        "dimension": 4, "batch_size": 8, "timeout_seconds": 30,
    }}}
    ai_path, embedding_path = directory / "ai-providers.yml", directory / "embedding-providers.yml"
    ai_path.write_text(yaml.safe_dump(ai), encoding="utf-8")
    embedding_path.write_text(yaml.safe_dump(embedding), encoding="utf-8")
    return ai_path, embedding_path


class Runtime:
    def __init__(self, workspace: Path, mode: str, image: str, *, mock_script: Path | None = None):
        self.workspace, self.mode = workspace, mode
        self.workspace.mkdir()
        self.project = "memory-os-v05-" + workspace.name[-12:]
        self.manifest = workspace / "compose.json"
        self.empty_env = workspace / "empty.env"
        self.empty_env.write_text("", encoding="utf-8")
        self.compose = ["docker", "compose", "--env-file", str(self.empty_env),
                        "--project-name", self.project, "-f", str(self.manifest)]
        self.database = workspace / "data/memory.db"
        self.vault = workspace / "knowledge"
        self.database.parent.mkdir()
        self.vault.mkdir()
        self.mock_process = None
        self.mock_log = None
        self.app = None
        self.compose_owned = False
        self.image = image
        self.mock_script = mock_script or PROJECT_ROOT / "scripts/v05_mock_server.py"
        self.base_url = ""

    def command(self, arguments: list[str], *, timeout=200) -> str:
        environment = {key: value for key, value in os.environ.items() if not key.startswith("MEMORY_OS_")}
        result = subprocess.run(arguments, cwd=PROJECT_ROOT, env=environment, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        with (self.workspace / "docker.log").open("a", encoding="utf-8") as output:
            output.write(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"Isolated Docker command failed; see {self.workspace / 'docker.log'}")
        return result.stdout.strip()

    def start_mock(self) -> str:
        port = free_port()
        self.mock_log = (self.workspace / "mock.log").open("a", encoding="utf-8")
        self.mock_process = subprocess.Popen(
            [sys.executable, str(self.mock_script), "--port", str(port),
             "--records", str(self.workspace / "mock-requests.jsonl")], cwd=PROJECT_ROOT,
            env={**os.environ, **isolated_proxy_environment()}, stdout=self.mock_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        url = f"http://127.0.0.1:{port}"
        eventually(lambda: self.healthy(url))
        return url

    @staticmethod
    def healthy(url: str) -> bool:
        with build_opener(ProxyHandler({})).open(url + "/health", timeout=3) as response:
            return response.status == 200

    def start(self) -> API:
        model_url = self.start_mock() if self.mode == "local" else "http://mock_model:9000"
        ai_path, embedding_path = profiles(self.workspace, model_url)
        services = {"qdrant": {"image": QDRANT_IMAGE, "pull_policy": "never",
                    "ports": ["127.0.0.1::6333"], "volumes": ["vectors:/qdrant/storage"],
                    "networks": ["frontend", "models"]}}
        if self.mode == "docker":
            environment = {"MEMORY_OS_DATABASE_URL": "sqlite:////app/data/memory.db",
                "MEMORY_OS_KNOWLEDGE_DIR": "/app/knowledge", "MEMORY_OS_SYNC_ENABLED": "true",
                "MEMORY_OS_SYNC_INTERVAL": "0.2", "MEMORY_OS_DELETION_GRACE": "1",
                "MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_CONFIG_FILE": "/app/config/ai-providers.yml",
                "MEMORY_OS_AI_DEFAULT_PROFILE": "offline", "MEMORY_OS_AI_KEYS__VERIFICATION": "verification-only-key",
                "MEMORY_OS_RAG_ENABLED": "true", "MEMORY_OS_EMBEDDING_CONFIG_FILE": "/app/config/embedding-providers.yml",
                "MEMORY_OS_EMBEDDING_DEFAULT_PROFILE": "offline", "MEMORY_OS_RAG_QDRANT_URL": "http://qdrant:6333",
                "MEMORY_OS_RAG_INTERVAL": "0.3", **isolated_proxy_environment()}
            services["api"] = {"image": self.image, "pull_policy": "never", "environment": environment,
                "ports": ["127.0.0.1::8000"], "stop_grace_period": "150s", "networks": ["frontend", "models"],
                "volumes": [f"{self.database.parent.as_posix()}:/app/data", f"{self.vault.as_posix()}:/app/knowledge",
                            f"{ai_path.parent.as_posix()}:/app/config:ro"]}
            services["mock_model"] = {"image": self.image, "pull_policy": "never", "networks": ["models"],
                "entrypoint": ["/usr/local/bin/python", "/mock/v05_mock_server.py", "--host", "0.0.0.0",
                               "--port", "9000", "--records", "/evidence/mock-requests.jsonl"],
                "healthcheck": {"disable": True}, "environment": isolated_proxy_environment(),
                "volumes": [f"{self.mock_script.as_posix()}:/mock/v05_mock_server.py:ro",
                            f"{self.workspace.as_posix()}:/evidence"]}
        manifest = {"services": services, "volumes": {"vectors": {}},
                    "networks": {"frontend": {}, "models": {"internal": True}}}
        json_file(self.manifest, manifest)
        self.compose_owned = True
        self.command(self.compose + ["up", "-d", "qdrant"])
        qdrant_url = "http://" + self.command(self.compose + ["port", "qdrant", "6333"])
        def qdrant_ready():
            with build_opener(ProxyHandler({})).open(qdrant_url + "/collections", timeout=3) as response:
                return response.status == 200
        eventually(qdrant_ready, timeout=90)
        if self.mode == "local":
            self.app = RunningApp(self.workspace)
            self.app.ai_environment = {"MEMORY_OS_AI_ENABLED": "true", "MEMORY_OS_AI_CONFIG_FILE": str(ai_path),
                "MEMORY_OS_AI_DEFAULT_PROFILE": "offline", "MEMORY_OS_AI_KEYS__VERIFICATION": "verification-only-key",
                "MEMORY_OS_RAG_ENABLED": "true", "MEMORY_OS_EMBEDDING_CONFIG_FILE": str(embedding_path),
                "MEMORY_OS_EMBEDDING_DEFAULT_PROFILE": "offline", "MEMORY_OS_RAG_QDRANT_URL": qdrant_url,
                "MEMORY_OS_RAG_INTERVAL": "0.3"}
            self.app.migrate()
            self.app.start()
            self.base_url = f"http://127.0.0.1:{self.app.port}"
        else:
            self.command(self.compose + ["up", "-d", "mock_model"])
            self.command(self.compose + ["run", "--rm", "--no-deps", "api", "/app/.venv/bin/alembic", "upgrade", "head"])
            self.command(self.compose + ["up", "-d", "api"])
            self.base_url = "http://" + self.command(self.compose + ["port", "api", "8000"])
            eventually(lambda: self.healthy(self.base_url), timeout=90)
        return API(self.base_url, self.vault)

    def restart(self) -> API:
        if self.mode == "local":
            self.app.stop()
            self.app.start()
            self.base_url = f"http://127.0.0.1:{self.app.port}"
        else:
            self.command(self.compose + ["up", "-d", "--force-recreate", "api", "qdrant"])
            self.base_url = "http://" + self.command(self.compose + ["port", "api", "8000"])
            eventually(lambda: self.healthy(self.base_url), timeout=90)
        return API(self.base_url, self.vault)

    def stop(self) -> None:
        errors = []
        for cleanup in (lambda: self.app.stop() if self.app else None,
                        lambda: self.command(self.compose + ["logs", "--no-color"], timeout=30) if self.compose_owned else None,
                        lambda: self.command(self.compose + ["down", "--volumes", "--remove-orphans"], timeout=200)
                        if self.compose_owned else None):
            try:
                cleanup()
            except Exception as error:
                errors.append(type(error).__name__)
        if self.mock_process:
            self.mock_process.terminate()
            try:
                self.mock_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.mock_process.kill()
                self.mock_process.wait(timeout=10)
        if self.mock_log:
            self.mock_log.close()
        json_file(self.workspace / "cleanup.json", {"errors": errors, "project": self.project})
        if errors:
            raise RuntimeError("Owned-resource cleanup failed; inspect cleanup.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["local", "docker", "all"], default="all")
    parser.add_argument("--image", default="memory-os-v05-validation:latest")
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    root = PROJECT_ROOT.resolve()
    cache = (root / ".cache/v05-validation").resolve()
    if not cache.is_relative_to(root):
        raise RuntimeError("Verification workspace must stay in the project")
    cache.mkdir(parents=True, exist_ok=True)
    workspace = cache / uuid4().hex
    workspace.mkdir()
    before = storage_fingerprint()
    import tomllib
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    report = {"version": version, "qdrant_image": QDRANT_IMAGE, "real_model_calls": 0,
              "quality_acceptance": "pending", "modes": {}, "formal_before": before}
    print(f"Evidence: {workspace}", flush=True)
    helper = Runtime(workspace / "setup", "local", args.image)
    try:
        if not args.skip_build:
            helper.command(["docker", "build", "-t", args.image, "."], timeout=600)
        helper.command(["docker", "image", "inspect", QDRANT_IMAGE])
        for mode in (["local", "docker"] if args.mode == "all" else [args.mode]):
            runtime = Runtime(workspace / f"{mode}-{uuid4().hex[:12]}", mode, args.image)
            try:
                app = runtime.start()
                state = run_workflow(app, runtime.workspace)
                app = runtime.restart()
                check_restart(app, state)
                with closing(sqlite3.connect(runtime.database)) as database:
                    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    assert database.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0004"
                report["modes"][mode] = {"status": "passed", "evidence": str(runtime.workspace)}
                print(f"{mode}: passed", flush=True)
            finally:
                runtime.stop()
        report["status"] = "engineering_passed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        print(f"Verification failed: {error}", file=sys.stderr, flush=True)
    finally:
        after = storage_fingerprint()
        report["formal_storage_unchanged"] = before == after
        if before != after:
            report["status"] = "failed"
        json_file(workspace / "report.json", report)
    return 0 if report["status"] == "engineering_passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
