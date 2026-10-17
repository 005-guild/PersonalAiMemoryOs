"""Local-only RAG acceptance helpers; never manage shared Docker resources."""

from __future__ import annotations

import asyncio
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from threading import Lock
import time
from urllib.parse import urlsplit

import httpx

from app.repositories.rag import collection_metadata
from app.vector.embedding import EmbeddingClient
from app.vector.qdrant import QdrantClient


def local_url(value: str) -> str:
    """This tool is intentionally incapable of testing a remote model service."""
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or "\\" in value or any(character.isspace() for character in value)):
        raise ValueError("Verification endpoints must use local HTTP without credentials.")
    parsed.port
    return value.rstrip("/")


def json_file(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(base_url: str, path: str) -> dict:
    with httpx.Client(trust_env=False, timeout=15) as client:
        response = client.get(base_url + path)
        response.raise_for_status()
        return response.json()


def generations(database: Path) -> list[dict]:
    if not database.exists():
        return []
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='rag_index_generations'").fetchone()
        return [dict(row) for row in connection.execute(
            "SELECT id,owner_id,collection,dimension,status FROM rag_index_generations"
        )] if exists else []


def owned_cleanup(database: Path, qdrant_url: str) -> list[dict]:
    """Only SQLite-owned collections with matching remote metadata can be removed."""
    removed = []
    for generation in generations(database):
        asyncio.run(QdrantClient(qdrant_url).delete_collection(
            generation["collection"], collection_metadata(generation)))
        removed.append({"collection": generation["collection"], "owner_id": generation["owner_id"]})
    return removed


class MeasuredEmbedding(EmbeddingClient):
    """Real local transport with counts and timings, not a synthetic model."""

    def __init__(self, expected_url: str):
        super().__init__()
        self.expected_url = expected_url
        self.records: list[dict] = []
        self.lock = Lock()

    @property
    def count(self) -> int:
        with self.lock:
            return len(self.records)

    async def embed(self, resolved, texts):
        if resolved.profile.base_url != self.expected_url:
            raise AssertionError("An unexpected Embedding service was selected.")
        started = time.monotonic()
        row = {"model": resolved.profile.model, "input_count": len(texts),
               "input_hashes": [hashlib.sha256(text.encode()).hexdigest() for text in texts]}
        with self.lock:
            self.records.append(row)
        try:
            reply = await super().embed(resolved, texts)
            assert all(len(vector) == 1024 and all(math.isfinite(number) for number in vector)
                       and any(vector) for vector in reply.vectors)
            row.update(status="passed", dimensions=[len(vector) for vector in reply.vectors], usage=reply.usage)
            return reply
        except BaseException as error:
            row.update(status="failed", error_type=type(error).__name__)
            raise
        finally:
            row["seconds"] = round(time.monotonic() - started, 4)


class ForbiddenGeneration:
    """Fail closed if any flow unexpectedly attempts text generation."""

    def __init__(self):
        self.calls = 0

    async def generate(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Text generation is forbidden during local retrieval acceptance.")

    async def aclose(self):
        pass


def request(client, method: str, path: str, body=None):
    response = client.request(method, path, **({"json": body} if body is not None else {}))
    if not response.is_success:
        raise AssertionError(f"{method} {path}: HTTP {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else None


def database_audit(database: Path) -> dict:
    with closing(sqlite3.connect(database)) as connection:
        counts = {name: connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("sources", "knowledge", "processing_runs", "processing_batches")}
        jobs = [{"id": row[0], "status": row[1], "version": row[2],
                 "vector_count": len(json.loads(row[3]) or []) if row[3] else 0,
                 "intent_count": len(json.loads(row[4]) or [])}
                for row in connection.execute("SELECT id,status,version,vectors,intents FROM rag_index_jobs")]
        return {"schema": connection.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_errors": connection.execute("PRAGMA foreign_key_check").fetchall(),
                "counts": counts, "jobs": jobs}
