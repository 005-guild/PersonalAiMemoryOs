"""Measure isolated Qdrant logical/allocated bytes from synthetic benchmark cache."""

import argparse
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
from uuid import uuid4

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.desktop.storage_backup import file_digest
from app.paths import portable_path
from app.vector.qdrant import QdrantClient
from benchmark_support import IsolatedQdrant, hardware_snapshot
from verification_support import isolated_proxy_environment


async def upload(url: str, generation: dict, jobs: list) -> int:
    remote = QdrantClient(url)
    name = "storage_" + uuid4().hex
    await remote.ensure_collection(name, generation["dimension"], {"purpose": "isolated_synthetic_storage", "owner_id": name})
    pending, count = [], 0
    for chunks, vectors, knowledge_id, content_hash in jobs:
        chunks, vectors = json.loads(chunks), json.loads(vectors)
        if len(chunks) != len(vectors):
            raise ValueError("Incomplete cached vector count")
        for chunk, vector in zip(chunks, vectors):
            pending.append({"id": chunk["id"], "vector": vector, "payload": {"knowledge_id": knowledge_id,
                "generation_id": generation["id"], "content_hash": content_hash, "ordinal": chunk["ordinal"]}})
            count += 1
            if len(pending) >= 128:
                await remote.upsert(name, pending)
                pending = []
    await remote.upsert(name, pending)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="Stopped synthetic benchmark SQLite under .cache")
    args = parser.parse_args()
    database = portable_path(ROOT / ".cache", args.database.absolute())
    if "capacity-baseline" not in database.relative_to(ROOT / ".cache").parts or not database.is_file():
        parser.error("Only a project-local synthetic capacity-baseline database is accepted")
    profile_file = portable_path(ROOT / ".cache", database.parent.parent / "config/embedding-providers.yml")
    declared = yaml.safe_load(profile_file.read_text(encoding="utf-8"))
    profile = declared["profiles"][declared["default_profile"]]
    if profile["model"] != "synthetic-hash-v1" or profile["base_url"] != "http://127.0.0.1:1/v1":
        parser.error("Expected the synthetic model label and unreachable transport used by the capacity harness")
    output = ROOT / ".cache/capacity-storage" / uuid4().hex
    output.mkdir(parents=True)
    before = file_digest(database)
    report = {"status": "failed", "hardware": hardware_snapshot(), "source_sha256": before,
              "real_model_calls": 0, "scope": "Cached synthetic vectors; bulk upload storage measurement, not indexing throughput"}
    resource = IsolatedQdrant()
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            generation = dict(connection.execute("SELECT * FROM rag_index_generations WHERE status='ready'").fetchone())
            jobs = connection.execute("SELECT j.chunks,j.vectors,j.knowledge_id,j.content_hash FROM rag_index_jobs j "
                "JOIN rag_note_index_states s ON s.published_job_id=j.id WHERE j.generation_id=? AND j.status='published'",
                (generation["id"],)).fetchall()
            if generation["profile_id"] != "local_bge_m3" or not jobs:
                raise ValueError("Unexpected benchmark profile or empty cache")
            if not all(json.loads(row[0]) for row in jobs):
                raise ValueError("Empty cached chunks")
            report["dimension"] = generation["dimension"]
        with patch.dict(os.environ, environment, clear=True):
            url = resource.start()
            report["points"] = asyncio.run(upload(url, generation, jobs))
            report["note_count"] = len(jobs)
            report["qdrant_apparent_bytes"] = resource.storage_bytes()
            report["qdrant_allocated_file_bytes"] = resource.allocated_bytes()
            report["status"] = "measured"
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
    finally:
        try:
            resource.stop()
            report["cleanup"] = "owned container and volume removed"
        except Exception as error:
            report.update(status="failed", cleanup_error=str(error))
        report["source_unchanged"] = before == file_digest(database)
        if not report["source_unchanged"]:
            report["status"] = "failed"
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output / "report.json")}))
    return 0 if report["status"] == "measured" else 1


if __name__ == "__main__":
    raise SystemExit(main())
