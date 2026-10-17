"""Isolated SQLite + real Qdrant throughput with synthetic vectors, no model calls."""

import argparse
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import sqlite3
import sys
import time
import traceback
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import insert
from app.main import create_app
from app.models import Knowledge, Source
from app.repositories.migrations import upgrade_database
from app.repositories.rag import RagRepository
from benchmark_support import IsolatedQdrant, SyntheticEmbedding, hardware_snapshot, timings
from local_rag_support import ForbiddenGeneration, request
from verification_support import isolated_proxy_environment
from verify_local_rag import prepare_settings
from v05_acceptance import storage_fingerprint


def timed(operation):
    start = time.perf_counter()
    value = operation()
    return value, time.perf_counter() - start


def stage(workspace, count, qdrant, qdrant_url):
    workspace.mkdir()
    settings = prepare_settings(workspace, "http://127.0.0.1:1/v1", "synthetic-hash-v1", "sha256-v1", qdrant_url)
    settings = settings.model_copy(update={"sync_enabled": False, "log_level": "ERROR"})
    upgrade_database(settings.database_url)
    synthetic, forbidden = SyntheticEmbedding(), ForbiddenGeneration()
    app = create_app(settings, embedding_client=synthetic, model_client=forbidden)
    metrics = {"notes": count, "source_records": count, "note_body_characters": 1500,
               "qdrant_storage_bytes_before_stage": qdrant.storage_bytes(),
               "chunk_chars": 1200, "overlap": 200, "vector_dimension": 1024,
               "model": "synthetic-hash-v1; NOT BGE-M3; no model/network inference"}
    # Run each complete index cycle explicitly on the app's own event loop, so
    # periodic cycles cannot contaminate list and incremental timing samples.
    with patch.object(app.state.rag_worker, "start", lambda: None):
        with TestClient(app) as client:
            with app.state.database.session() as session:
                notes = [{"id": str(uuid4()), "title": f"容量样例 {i}", "body": ("用于测量隔离索引和查询耗时的自编数据。" * 100)[:1500]}
                         for i in range(count)]
                session.execute(insert(Knowledge), notes)
                session.execute(insert(Source), [{"title": f"分组标题 {i // 5}", "source_type": "synthetic", "content": "自编资料"} for i in range(count)])
                session.commit()
            lists, groups = [], []
            for _ in range(10):
                _, duration = timed(lambda: request(client, "GET", "/api/v1/ui/knowledge?limit=100"))
                lists.append(duration)
                _, duration = timed(lambda: request(client, "GET", "/api/v1/ui/source-groups?limit=100&sort_by=source_count"))
                groups.append(duration)
            metrics.update(knowledge_list=timings(lists), grouped_source_list=timings(groups))
            _, metrics["first_index_seconds"] = timed(lambda: client.portal.call(app.state.rag_index.run_once))
            index = request(client, "GET", "/api/v1/rag/index/status?summary_only=true")
            assert index["counts"]["published"] == count and not index["last_error"]
            before = synthetic.calls
            _, metrics["unchanged_reconcile_seconds"] = timed(lambda: client.portal.call(app.state.rag_index.run_once))
            assert synthetic.calls == before
            first = request(client, "GET", "/api/v1/knowledge/" + notes[0]["id"])
            request(client, "PATCH", "/api/v1/knowledge/" + first["id"],
                    {"expected_version": first["version"], "body": first["body"] + "增量变更标记"})
            _, metrics["one_note_update_seconds"] = timed(lambda: client.portal.call(app.state.rag_index.run_once))
            searches = []
            for _ in range(10):
                _, duration = timed(lambda: request(client, "POST", "/api/v1/rag/search", {"query": "隔离容量测量", "top_k": 5}))
                searches.append(duration)
            metrics["search"] = timings(searches)
            metrics["qdrant_storage_bytes_during_run"] = qdrant.storage_bytes()
            metrics["qdrant_allocated_file_bytes_during_run"] = qdrant.allocated_bytes()
            metrics["synthetic_embedding_calls"] = synthetic.calls
            # Explicit full reconciliation at this size includes current N+1
            # repository snapshots; future optimizations must retain filtering.
            metrics["published"] = index["counts"]["published"]
            assert forbidden.calls == 0
    database = workspace / "data/memory.db"
    metrics["sqlite_bytes"] = database.stat().st_size
    with closing(sqlite3.connect(database)) as connection:
        metrics["cached_vector_json_bytes"] = connection.execute("SELECT coalesce(sum(length(vectors)),0) FROM rag_index_jobs").fetchone()[0]
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notes", type=int, nargs="+", default=[100, 1000])
    args = parser.parse_args()
    if any(n < 1 or n > 10000 for n in args.notes):
        parser.error("Each stage must contain 1..10000 notes")
    output = ROOT / ".cache/capacity-baseline" / uuid4().hex
    output.mkdir(parents=True)
    before = storage_fingerprint()
    qdrant = IsolatedQdrant()
    report = {"status": "failed", "hardware": hardware_snapshot(), "platform": platform.platform(), "processor": platform.processor(),
        "cpu_count": os.cpu_count(), "real_model_calls": 0, "generation_calls": 0,
        "scope": "Warm local process; real isolated Qdrant/SQLite; synthetic 1024D vectors, NOT embedding throughput", "stages": []}
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    logging.basicConfig(level=logging.ERROR)
    try:
        with patch.dict(os.environ, environment, clear=True):
            url = qdrant.start()
            for number, count in enumerate(args.notes):
                print(f"Benchmarking {count} notes...", flush=True)
                report["stages"].append(stage(output / f"stage-{number}", count, qdrant, url))
                (output / "progress.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["status"] = "measured"
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
        (output / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        try:
            qdrant.stop()
            report["cleanup"] = "owned container and named volume removed"
        except Exception as error:
            report.update(status="failed", cleanup_error=str(error))
        report["formal_storage_unchanged"] = before == storage_fingerprint()
        if not report["formal_storage_unchanged"]:
            report["status"] = "failed"
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output / "report.json")}))
    return 0 if report["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
