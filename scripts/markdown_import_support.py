"""Read-only corpus evidence and isolated local runtime for Markdown acceptance."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".avif"}
EXPECTED_TYPES = {"answer": 522, "article": 41, "pin": 8}
ENDPOINT = "/api/v1/imports/zhihu-markdown"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(url: str) -> tuple[str, str]:
    path = urlsplit(url).path.rstrip("/")
    for pattern, kind in ((r"/question/\d+/answer/(\d+)", "answer"),
                          (r"/p/(\d+)", "article"), (r"/pin/(\d+)", "pin")):
        match = re.fullmatch(pattern, path)
        if match:
            return kind, match.group(1)
    raise AssertionError("The real export contains an unrecognized Zhihu identity")


class ExportCorpus:
    """Never write, modify or copy original Markdown/images; retain hashes only."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.before = self.snapshot()
        self.entries = {}
        self.image_hashes = set()
        self.total_bytes = 0
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            if path.suffix.lower() in IMAGE_SUFFIXES:
                self.image_hashes.add(self.before[relative])
            if path.suffix.lower() != ".md" or path.name.lower() == "readme.md":
                continue
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
            opening = re.match(r"\A---(?:\r\n|\n)", text)
            assert opening, "Missing real-export frontmatter opening"
            closing = re.search(r"(?m)^---(?:\r\n|\n|$)", text[opening.end():])
            assert closing, "Missing real-export frontmatter closing"
            start, end = opening.end() + closing.start(), opening.end() + closing.end()
            header = yaml.safe_load(text[opening.end():start])
            body = text[end:]
            assert isinstance(header, dict) and body.strip()
            kind, external_id = identity(header["source"])
            self.entries[relative] = {
                "title": header["title"], "author": header.get("author"), "url": header["source"],
                "resource_type": kind, "external_id": external_id,
                "content_hash": digest(body.encode("utf-8")), "text_hash": digest(text.encode("utf-8")),
            }
            self.total_bytes += len(raw)
        assert len(self.entries) == 571, "The expected real corpus must contain 571 importable Markdown files"
        assert dict(Counter(item["resource_type"] for item in self.entries.values())) == EXPECTED_TYPES

    def snapshot(self) -> dict[str, str]:
        return {path.relative_to(self.root).as_posix(): digest(path.read_bytes())
                for path in sorted(self.root.rglob("*")) if path.is_file()}

    def path_key(self, value: str) -> str:
        value = value.replace("\\", "/")
        prefix = self.root.name + "/"
        value = value[len(prefix):] if value.startswith(prefix) else value
        assert value in self.entries, "Upload/report includes a file outside the selected Markdown corpus"
        return value

    def check_upload(self, payload: dict) -> dict:
        assert set(payload) == {"files"} and len(payload["files"]) == 571
        keys = []
        for item in payload["files"]:
            assert set(item) == {"relative_path", "content"}
            key = self.path_key(item["relative_path"])
            assert digest(item["content"].encode("utf-8")) == self.entries[key]["text_hash"]
            keys.append(key)
        assert len(set(keys)) == len(self.entries)
        return {"files": len(keys), "only_markdown": True, "exact_utf8_text_hashes": True}

    def summary(self) -> dict:
        packed = "\n".join(f"{path}\0{hash_value}" for path, hash_value in self.before.items()).encode("utf-8")
        return {"importable_markdown": len(self.entries), "all_original_files": len(self.before),
                "types": EXPECTED_TYPES, "markdown_bytes": self.total_bytes,
                "original_tree_sha256": digest(packed), "export_image_hashes": len(self.image_hashes)}

    def check_image_copies(self, runtime: Path) -> int:
        copies = [path for path in runtime.rglob("*") if path.is_file()
                  and "_internal" not in path.parts and path.suffix.lower() in IMAGE_SUFFIXES
                  and digest(path.read_bytes()) in self.image_hashes]
        assert not copies, "An original export image was copied into runtime storage"
        return 0


def assert_public_report(value):
    if isinstance(value, dict):
        assert not ({"content", "body", "markdown", "raw", "raw_markdown"} & set(value)), "Report contains source body fields"
        for entry in value.values():
            assert_public_report(entry)
    elif isinstance(value, list):
        for entry in value:
            assert_public_report(entry)


def check_report(report: dict, corpus: ExportCorpus, *, stage: str):
    assert_public_report(report)
    assert report["total"] == report["processed"] == 571
    assert report["invalid"] == report["failed"] == 0
    assert len(report["items"]) == 571
    assert Counter(item["resource_type"] for item in report["items"]) == Counter(EXPECTED_TYPES)
    assert {corpus.path_key(item["relative_path"]) for item in report["items"]} == set(corpus.entries)
    if stage == "preview":
        assert report["dry_run"] and report["would_create"] == 571 and report["created"] == 0
    elif stage == "created":
        assert not report["dry_run"] and report["created"] == 571
    else:
        assert report["created"] == report["would_create"] == 0 and report["skipped"] == 571


def verify_storage(database: Path, corpus: ExportCorpus, created: dict) -> dict:
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 571
        assert connection.execute("SELECT COUNT(*) FROM source_origins").fetchone()[0] == 571
        for table in ("knowledge", "processing_runs", "rag_index_generations", "rag_note_index_states", "rag_index_jobs"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        records = {row["id"]: row for row in connection.execute("SELECT * FROM sources")}
        origins = {row["source_id"]: row for row in connection.execute("SELECT * FROM source_origins")}
        for item in created["items"]:
            expected = corpus.entries[corpus.path_key(item["relative_path"])]
            row, origin = records[item["source_id"]], origins[item["source_id"]]
            assert row["source_type"] == "zhihu" and row["version"] == 1 and row["deleted_at"] is None
            assert row["title"] == expected["title"] and row["author"] == expected["author"]
            assert identity(row["url"]) == (expected["resource_type"], expected["external_id"])
            assert digest(row["content"].encode("utf-8")) == expected["content_hash"]
            assert origin["resource_type"] == expected["resource_type"] and origin["external_id"] == expected["external_id"]
    return {"sources": 571, "origins": 571, "content_hashes_verified": 571, "types": EXPECTED_TYPES,
            "knowledge": 0, "processing_runs": 0, "rag_records": 0, "sqlite_integrity": "ok"}


def request_json(url: str, path: str) -> dict:
    with build_opener(ProxyHandler({})).open(Request(url + path), timeout=120) as response:
        return json.load(response)


class LocalMarkdownRuntime:
    """Use the existing real Uvicorn lifecycle with no personal dotenv or keys."""

    def __init__(self, root: Path):
        from app.config import Settings
        from app.repositories.migrations import upgrade_database
        self.root = root
        self.settings = Settings(_env_file=None, runtime_root=root,
            database_url=f"sqlite:///{(root / 'data/memory.db').as_posix()}",
            knowledge_dir=str(root / "knowledge"), sync_enabled=False, ai_enabled=False, rag_enabled=False,
            ai_keys={}, ai_config_file=str(root / "config/absent-ai.yml"),
            embedding_config_file=str(root / "config/absent-embedding.yml"))
        upgrade_database(self.settings.database_url)
        self.backend = None
        self.url = ""

    def start(self):
        from app.desktop.server import DesktopServer
        self.backend = DesktopServer(self.settings)
        self.backend.start()
        self.url = self.backend.url

    def request(self, method, path):
        assert method == "GET"
        return request_json(self.url, path)

    def stop(self):
        if self.backend:
            self.backend.stop()
            self.backend = None
