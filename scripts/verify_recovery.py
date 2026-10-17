"""Isolated full backup/restore drill with real LOCAL BGE-M3/Qdrant; no paid calls."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import traceback
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.desktop.storage_backup import backup_storage, file_digest
from app.desktop.update import _legacy_snapshot
from app.main import create_app
from app.repositories.migrations import upgrade_database
from app.repositories.rag import collection_metadata
from app.vector.qdrant import QdrantClient
from local_rag_support import (ForbiddenGeneration, MeasuredEmbedding, database_audit,
                               generations, get_json, local_url, owned_cleanup, request)
from local_rag_workflow import check_restart, run_workflow
from recovery_support import backup_configuration, restore_new, verify_backup
from verification_support import isolated_proxy_environment
from verify_local_rag import prepare_settings
from v05_acceptance import storage_fingerprint


def run(embedding_url: str, qdrant_url: str) -> tuple[dict, Path]:
    embedding_url, qdrant_url = local_url(embedding_url), local_url(qdrant_url)
    workspace = ROOT / ".cache/recovery-validation" / uuid4().hex
    original, restored = workspace / "original", workspace / "restored"
    original.mkdir(parents=True)
    database = original / "data/memory.db"
    report = {"status": "failed", "generation_calls": 0, "route": "SQLite cached vectors; not Qdrant snapshot"}
    measured, forbidden = MeasuredEmbedding(embedding_url), ForbiddenGeneration()
    before, started = storage_fingerprint(), time.monotonic()
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    try:
        with patch.dict(os.environ, environment, clear=True):
            models = get_json(embedding_url.removesuffix("/v1"), "/api/tags")["models"]
            model = next(m for m in models if m["name"] == "bge-m3:latest")
            report["model_digest"] = model["digest"]
            report["collections_before"] = get_json(qdrant_url, "/collections")["result"]["collections"]
            settings = prepare_settings(original, embedding_url, "bge-m3", model["digest"], qdrant_url)
            (original / ".env").write_text("MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=false\n", encoding="utf-8")
            (original / "config/local-rag-startup.json").write_text(
                '{"schema_version":1,"enabled":false,"project_root":"../.."}', encoding="utf-8")
            upgrade_database(settings.database_url)
            with TestClient(create_app(settings, embedding_client=measured, model_client=forbidden)) as client:
                state = run_workflow(client, original, measured)
                # Exercise all-source provenance in the restored library as well.
                second = request(client, "POST", "/api/v1/sources", {"title": "第二来源", "content": "恢复关系验证"})
                note = request(client, "GET", "/api/v1/knowledge/" + state["knowledge_ids"][1])
                request(client, "PATCH", "/api/v1/knowledge/" + note["id"],
                        {"expected_version": note["version"], "source_ids": [state["source_id"], second["id"]]})
            # Both source and restored processes are stopped during snapshot and comparison.
            snapshot = _legacy_snapshot(database)
            saved = backup_storage(original, database, original / "knowledge", "0006")
            backup_configuration(original, saved)
            manifest = verify_backup(saved)
            report["restore"] = restore_new(saved, restored)
            assert snapshot == _legacy_snapshot(restored / "data/memory.db")
            assert all(file_digest(restored / name) == digest for name, digest in manifest["configuration"].items())
            assert all(file_digest(restored / name) == digest for name, digest in manifest["files"].items() if name.startswith("knowledge/"))
            restored_settings = settings.model_copy(update={
                "runtime_root": restored, "database_url": f"sqlite:///{(restored / 'data/memory.db').as_posix()}",
                "rag_enabled": False, "ai_enabled": False})
            before_off = measured.count
            with TestClient(create_app(restored_settings, embedding_client=measured, model_client=forbidden)) as client:
                assert client.get("/health").status_code == 200
                assert request(client, "GET", "/api/v1/ui/knowledge?state=all")["total"] == 3
            assert measured.count == before_off
            # The original isolated app stays OFF. Remove only its owned remote
            # collection, simulating lost Qdrant storage; recover from SQLite cache.
            for generation in generations(database):
                asyncio.run(QdrantClient(qdrant_url).delete_collection(generation["collection"], collection_metadata(generation)))
            report["rag_off_first_start_embedding_calls"] = 0
            with TestClient(create_app(restored_settings.model_copy(update={"rag_enabled": True}),
                                      embedding_client=measured, model_client=forbidden)) as client:
                report["cache_recovery"] = check_restart(client, state, measured)
            report["database"] = database_audit(restored / "data/memory.db")
            assert report["database"]["integrity"] == "ok" and not report["database"]["foreign_key_errors"]
            report.update(status="passed", all_rows_identical_before_startup=True,
                          configuration_hashes_retained=True, full_vault_hashes_retained=True)
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
        (workspace / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        try:
            with patch.dict(os.environ, environment, clear=True):
                # Same isolated owner, never running concurrently; either DB can
                # identify its resources, including failures before restoration.
                report["cleanup"] = owned_cleanup(database, qdrant_url)
                report["collections_after"] = get_json(qdrant_url, "/collections")["result"]["collections"]
                assert report.get("collections_before") == report["collections_after"]
        except Exception as error:
            report.update(status="failed", cleanup_error=str(error))
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        report["generation_calls"] = forbidden.calls
        report["embedding_requests"] = measured.records
        report["seconds"] = round(time.monotonic() - started, 3)
        if not report["formal_storage_unchanged"] or forbidden.calls:
            report["status"] = "failed"
        (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, workspace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    args = parser.parse_args()
    result, evidence = run(args.embedding_url, args.qdrant_url)
    print(json.dumps({"status": result["status"], "report": str(evidence / "report.json")}, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "passed" else 1)
