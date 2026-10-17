"""The real-model verification tool must remain local and isolated by construction."""

import asyncio
import importlib
from pathlib import Path
import sqlite3

import pytest


@pytest.fixture
def support(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("local_rag_support")


@pytest.mark.parametrize("url", [
    "https://api.example.test/v1", "http://example.test/v1", "http://127.0.0.1@evil.test/v1",
    "http://secret@127.0.0.1/v1", "http://127.0.0.1/v1?key=secret", "http://127.0.0.1/v1#fragment",
    "http://127.0.0.1:invalid/v1", "http://127.0.0.1\\@example.test/v1", "http://127.0.0.1/v1 ",
])
def test_validation_rejects_remote_or_credentialed_endpoints(support, url):
    with pytest.raises(ValueError):
        support.local_url(url)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:11434/v1", "http://localhost:6333", "http://[::1]:6333",
])
def test_validation_accepts_loopback_endpoints(support, url):
    assert support.local_url(url + "/") == url


def test_collection_cleanup_only_uses_the_selected_database_and_checks_ownership(support, tmp_path, monkeypatch):
    database = tmp_path / "memory.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE rag_index_generations (id TEXT,owner_id TEXT,collection TEXT,dimension INT,status TEXT)")
        connection.execute("INSERT INTO rag_index_generations VALUES (?,?,?,?,?)",
            ("isolated-generation", "isolated-owner", "memory_os_test_only", 1024, "ready"))
    observed = []
    class GuardedClient:
        def __init__(self, base_url):
            assert base_url == "http://127.0.0.1:6333"
        async def delete_collection(self, name, metadata):
            observed.append((name, metadata))
    monkeypatch.setattr(support, "QdrantClient", GuardedClient)
    removed = support.owned_cleanup(database, "http://127.0.0.1:6333")
    assert removed == [{"collection": "memory_os_test_only", "owner_id": "isolated-owner"}]
    assert observed == [("memory_os_test_only", {"application": "personal-ai-memory-os",
        "generation_id": "isolated-generation", "owner_id": "isolated-owner"})]
    assert support.owned_cleanup(tmp_path / "absent.db", "http://127.0.0.1:6333") == []


def test_generation_transport_fails_closed(support):
    forbidden = support.ForbiddenGeneration()
    with pytest.raises(AssertionError, match="forbidden"):
        asyncio.run(forbidden.generate("unexpected prompt"))
    assert forbidden.calls == 1


def test_preparation_uses_only_explicit_isolated_configuration(support, monkeypatch, tmp_path):
    module = importlib.import_module("verify_local_rag")
    monkeypatch.setenv("MEMORY_OS_AI_ENABLED", "true")
    monkeypatch.setenv("MEMORY_OS_AI_KEYS__PRIVATE", "must-not-be-loaded")
    monkeypatch.setenv("MEMORY_OS_RAG_ENABLED", "false")
    # Main clears application variables before calling prepare_settings.
    from unittest.mock import patch
    with patch.dict("os.environ", {}, clear=True):
        settings = module.prepare_settings(tmp_path, "http://127.0.0.1:11434/v1", "bge-m3",
            "fixture-digest", "http://127.0.0.1:6333")
    assert settings.runtime_root == tmp_path and settings.ai_enabled is False
    assert settings.ai_keys == {} and settings.rag_enabled is True
    assert settings.knowledge_path.is_relative_to(tmp_path)
    assert Path(settings.database_url.removeprefix("sqlite:///")).is_relative_to(tmp_path)


def test_database_audit_handles_cleared_json_null_vector_cache(support, tmp_path):
    database = tmp_path / "memory.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version(version_num TEXT)")
        connection.execute("INSERT INTO alembic_version VALUES('0006')")
        for table in ("sources", "knowledge", "processing_runs", "processing_batches"):
            connection.execute(f"CREATE TABLE {table}(id TEXT)")
        connection.execute("CREATE TABLE rag_index_jobs(id TEXT,status TEXT,version INT,vectors TEXT,intents TEXT)")
        connection.execute("INSERT INTO rag_index_jobs VALUES('old','superseded',1,'null','[]')")
    audit = support.database_audit(database)
    assert audit["integrity"] == "ok" and audit["jobs"][0]["vector_count"] == 0
