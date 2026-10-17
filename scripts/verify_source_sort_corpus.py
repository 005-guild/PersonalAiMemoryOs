"""Verify all eight group orderings using a copy of an existing cache database.

Run from the project root:
  uv run python scripts/verify_source_sort_corpus.py --database .cache/.../memory.db

Only a project-local .cache input is accepted. The input must already be closed
and checkpointed; no corpus files, current installations or providers are opened.
Reports contain aggregate counts and hashes, never source titles or article text.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import event, select

from app.models import Source
from app.paths import portable_path
from app.repositories.database import Database
from app.repositories.migrations import check_schema
from app.services.ui import UIService

DEFAULT_INPUT = PROJECT_ROOT / ".cache/source-group-corpus/82da5e247698417e92588e8ee20168fc/memory.db"
SORTS = ("title", "source_count", "source_type", "updated_at")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def table_snapshot(path: Path) -> dict:
    """Hash actual values of every user table, including the Alembic revision."""
    def quote(name):
        return '"' + name.replace('"', '""') + '"'

    snapshot = {}
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        for name in names:
            columns = connection.execute("PRAGMA table_info(" + quote(name) + ")").fetchall()
            primary = [column[1] for column in sorted(columns, key=lambda column: column[5]) if column[5]]
            ordering = primary or [column[1] for column in columns]
            query = "SELECT * FROM " + quote(name) + " ORDER BY " + ",".join(map(quote, ordering))
            digest = hashlib.sha256(encoded([column[1] for column in columns]))
            count = 0
            for row in connection.execute(query):
                values = [["blob", value.hex()] if isinstance(value, bytes) else value for value in row]
                digest.update(b"\n" + encoded(values))
                count += 1
            snapshot[name] = {"rows": count, "sha256": digest.hexdigest()}
    finally:
        connection.close()
    return snapshot


def expected_groups(database: Database) -> list[dict]:
    """Derive expected grouping only from original Source metadata in Python."""
    with database.session() as session:
        rows = session.execute(select(Source.title, Source.source_type, Source.updated_at,
                                      Source.deleted_at)).all()
    grouped = defaultdict(list)
    for row in rows:
        if row.deleted_at is None:
            grouped[row.title].append(row)
    return [{"title": title, "source_count": len(members), "active_count": len(members),
             "deleted_count": 0, "latest_updated_at": max(member.updated_at for member in members),
             "source_types": sorted({member.source_type for member in members})}
            for title, members in grouped.items()]


def ordered_groups(groups: list[dict], sort_by: str, order: str) -> list[dict]:
    key = {"title": lambda group: group["title"],
           "source_count": lambda group: group["source_count"],
           "source_type": lambda group: min(group["source_types"]),
           "updated_at": lambda group: group["latest_updated_at"]}[sort_by]
    ordered = sorted(groups, key=lambda group: group["title"])
    ordered.sort(key=key, reverse=order == "desc")
    return ordered


def check_orderings(database: Database, groups: list[dict]) -> list[dict]:
    reports = []
    source_count = sum(group["source_count"] for group in groups)
    with database.session() as session:
        service = UIService(session)
        for sort_by in SORTS:
            for order in ("asc", "desc"):
                expected, collected = ordered_groups(groups, sort_by, order), []
                for offset in range(0, len(expected), 20):
                    page = service.source_groups(q="", state="active", offset=offset, limit=20,
                                                 sort_by=sort_by, order=order)
                    assert page["total"] == len(expected) and page["total_sources"] == source_count
                    assert page["items"] == expected[offset:offset + 20], "Global sorted page differs."
                    collected.extend(page["items"])
                assert collected == expected
                assert len({group["title"] for group in collected}) == len(expected)
                assert service.source_groups(q="", state="active", offset=len(expected), limit=20,
                                              sort_by=sort_by, order=order)["items"] == []
                reports.append({"sort_by": sort_by, "order": order, "groups_verified": len(expected),
                                "sources_covered": source_count, "pages_checked": (len(expected) + 19) // 20})
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    try:
        source = portable_path(PROJECT_ROOT, args.database.absolute())
        if not source.is_relative_to(PROJECT_ROOT / ".cache") or not source.is_file():
            raise ValueError()
        for suffix in ("-wal", "-journal"):
            sidecar = portable_path(PROJECT_ROOT, Path(str(source) + suffix))
            if sidecar.exists() and sidecar.stat().st_size:
                raise ValueError()
    except (ValueError, OSError):
        parser.error("Select an existing, closed/checkpointed database inside the project .cache directory.")
    evidence = portable_path(PROJECT_ROOT, PROJECT_ROOT / ".cache/source-sort-corpus" / uuid4().hex)
    evidence.mkdir(parents=True)
    destination = evidence / "memory.db"
    report = {"status": "running", "real_model_calls": 0, "formal_instances_accessed": False,
              "original_corpus_accessed": False, "report_contains_private_content": False,
              "input_database": source.relative_to(PROJECT_ROOT).as_posix()}
    database, initial_source_hash, listening = None, file_digest(source), False
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        shutil.copy2(source, destination)
        assert file_digest(destination) == initial_source_hash, "Database copy differs from source cache."
        before = table_snapshot(destination)
        database = Database(f"sqlite:///{destination.as_posix()}")
        database.initialize()
        check_schema(database.engine)
        event.listen(database.engine, "before_cursor_execute", capture)
        listening = True
        groups = expected_groups(database)
        assert groups, "The selected database has no active Sources."
        report["orderings"] = check_orderings(database, groups)
        assert statements and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
        report.update(source_count=sum(group["source_count"] for group in groups), title_groups=len(groups),
                      sql_write_statements=0, sql_select_statements=len(statements))
        after = table_snapshot(destination)
        assert before == after, "Source body/version or other table data changed during sorting."
        report.update(status="passed", tables_before=before, tables_after=after,
                      all_table_data_unchanged=True, data_sha256=digest_snapshot(before))
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
    finally:
        if database is not None:
            if listening:
                event.remove(database.engine, "before_cursor_execute", capture)
            database.dispose()
        try:
            report["input_cache_file_unchanged"] = initial_source_hash == file_digest(source)
            report["copy_file_unchanged"] = initial_source_hash == file_digest(destination) if destination.exists() else False
        except OSError as error:
            report.update(input_cache_file_unchanged=False, copy_file_unchanged=False,
                          final_file_check_error_type=type(error).__name__)
        report["input_cache_sha256"] = initial_source_hash
        if not report["input_cache_file_unchanged"] or not report["copy_file_unchanged"]:
            report["status"] = "failed"
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "source_count": report.get("source_count"),
                      "title_groups": report.get("title_groups"), "report": str(evidence / "report.json")}))
    return 0 if report["status"] == "passed" else 1


def digest_snapshot(snapshot: dict) -> str:
    return hashlib.sha256(encoded(snapshot)).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
