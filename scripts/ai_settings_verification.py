"""Synthetic-only storage and network oracles for frozen AI-settings acceptance."""

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from threading import Thread


@contextmanager
def unused_model_endpoint():
    """Count any accidental model traffic without reading credentials or bodies."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reject(self):
            calls.append({"method": self.command, "path": self.path.split("?", 1)[0]})
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"settings-must-not-call-a-model"}')

        do_GET = do_POST = do_PUT = do_DELETE = reject

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def seed_business_records(app):
    source = app.request("POST", "/api/v1/sources", {
        "title": "设置验收的独立原始资料", "source_type": "manual", "author": "合成作者",
        "content": "这份合成资料只验证设置保存不会修改业务数据，不需要任何模型处理。",
    })
    note = app.request("POST", "/api/v1/knowledge", {
        "source_id": source["id"], "title": "设置验收的独立笔记", "summary": "合成笔记摘要。",
        "body": "# 设置验收\n这是隔离数据；保存配置不应修改笔记。\n", "tags": ["合成验收"],
    })
    return source["id"], note["id"]


def business_snapshot(database: Path) -> dict:
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        result = {}
        for table in ("sources", "knowledge"):
            rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY id")]
            assert len(rows) == 1
            result[table] = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        for table in ("source_origins", "processing_runs", "rag_index_generations", "rag_note_index_states", "rag_index_jobs"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return result


def secret_absent(value, secret):
    assert secret not in json.dumps(value, ensure_ascii=False), "A write-only synthetic key was exposed."


def verify_private_files(runtime: Path, secret: str, profile_id: str, model_url: str):
    """Only the verifier's newly-created .cache copy is inspected, never user config."""
    assert ".cache" in runtime.parts
    environment = (runtime / ".env").read_text(encoding="utf-8")
    assert environment.count(secret) == 1
    assert f"MEMORY_OS_AI_KEYS__{profile_id.upper()}=" in environment
    assert "MEMORY_OS_AI_ENABLED" in environment
    import yaml
    yaml_path = runtime / "config/ai-providers.yml"
    raw_yaml = yaml_path.read_text(encoding="utf-8")
    document = yaml.safe_load(raw_yaml)
    assert secret not in raw_yaml
    assert document["default_profile"] == profile_id
    profile = document["profiles"][profile_id]
    assert profile["api_key_ref"] == profile_id and profile["base_url"] == model_url
    assert profile["enabled"] is True
    assert secret.encode() not in (runtime / "data/memory.db").read_bytes()
    for log in (runtime / "logs").rglob("*"):
        if log.is_file():
            assert secret.encode() not in log.read_bytes(), "A synthetic key appeared in a runtime log."
    journal = runtime / ".memory-os-config-transactions"
    assert not journal.exists() or not list(journal.iterdir()), "Credential transaction backups were retained."
    assert not list(runtime.rglob(".memory-os-ai-*.tmp")), "Credential temporary files were retained."
    return {"own_dotenv_has_synthetic_key": True, "yaml_contains_reference_only": True,
            "database_and_logs_exclude_key": True, "credential_backups_cleaned": True}
