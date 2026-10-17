"""Read a local Zhihu export and verify title grouping in isolated SQLite storage.

Run: uv run python scripts/verify_source_group_corpus.py
The corpus is never modified. Reports contain aggregate counts/hashes, not titles,
authors, client filenames or article text. The isolated database remains in .cache.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from threading import RLock
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select
import yaml

from app.models import Base, Source
from app.paths import portable_path
from app.repositories.database import Database
from app.repositories.migrations import upgrade_database
from app.services.importer import ImportService
from app.services.import_types import ParsedZhihuItem
from app.services.ui import UIService
from app.services.zhihu_markdown import parse_markdown_document
from app.services.zhihu_parser import normalize_zhihu_url

HEADER = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|\Z)", re.DOTALL | re.MULTILINE)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(corpus: Path) -> dict:
    """Hash every input file, including images, without storing private filenames."""
    files, total_bytes = {}, 0

    def fail(error):
        raise error

    for current, directories, names in os.walk(corpus, followlinks=False, onerror=fail):
        directories.sort()
        for name in directories:
            portable_path(corpus, Path(current) / name)
        for name in sorted(names):
            path = portable_path(corpus, Path(current) / name)
            if not path.is_file():
                raise RuntimeError("Input contains a non-regular file.")
            raw = path.read_bytes()
            files[digest(path.relative_to(corpus).as_posix().encode("utf-8"))] = digest(raw)
            total_bytes += len(raw)
    combined = digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
    return {"file_count": len(files), "total_bytes": total_bytes, "sha256": combined}


def read_corpus(corpus: Path) -> tuple[bytes, dict[int, dict]]:
    files, expected = [], {}
    for path in sorted(corpus.rglob("*")):
        if not path.is_file() or path.suffix.casefold() != ".md":
            continue
        portable_path(corpus, path)
        content = path.read_bytes().decode("utf-8-sig")
        index = len(files)
        files.append({"relative_path": path.relative_to(corpus).as_posix(), "content": content})
        if path.name.casefold() == "readme.md":
            continue
        # Independent extraction and Python Counter provide the expected groups;
        # no SQL grouping result is reused to derive expected counts or members.
        match = HEADER.match(content)
        if match is None or len(match.group(1)) > 64 * 1024:
            raise RuntimeError("The corpus contains unsupported frontmatter.")
        try:
            header = yaml.safe_load(match.group(1))
        except (yaml.YAMLError, ValueError, RecursionError):
            raise RuntimeError("The corpus contains invalid metadata.") from None
        if not isinstance(header, dict) or not isinstance(header.get("title"), str):
            raise RuntimeError("The corpus has no expected title metadata.")
        expected[index] = {"title": header["title"].strip(), "author": header.get("author"),
            "url": normalize_zhihu_url(header["source"]).canonical_url,
            "body_sha256": digest(content[match.end():].encode("utf-8"))}
    return json.dumps({"files": files}, ensure_ascii=False).encode("utf-8"), expected


def source_snapshot(database: Database) -> dict[str, dict]:
    with database.session() as session:
        rows = session.execute(select(Source.id, Source.title, Source.author, Source.url,
                                      Source.version, Source.deleted_at, Source.content))
        return {row.id: {"title": row.title, "author": row.author, "url": row.url,
            "version": row.version, "deleted_at": row.deleted_at,
            "body_sha256": digest(row.content.encode("utf-8"))} for row in rows}


def zero_side_effect_counts(database: Database, expected_sources: int) -> dict:
    with database.session() as session:
        counts = {table.name: int(session.scalar(select(func.count()).select_from(table)) or 0)
                  for table in Base.metadata.sorted_tables}
    assert counts.pop("sources") == expected_sources
    assert counts.pop("source_origins") == expected_sources
    assert all(count == 0 for count in counts.values()), "Unexpected knowledge/processing/sync/index writes."
    return counts


def check_groups(database: Database, expected: dict, imported) -> dict:
    title_counts = Counter(item["title"] for item in expected.values())
    expected_members = {}
    for item in imported.items:
        if item.status == "created":
            expected_members.setdefault(expected[item.index]["title"], set()).add(item.source_id)
    seen_titles, member_ids, groups = set(), set(), []
    page_count = math.ceil(len(title_counts) / 20)
    with database.session() as session:
        service = UIService(session)
        for page_number in range(page_count):
            page = service.source_groups(q="", state="active", offset=page_number * 20, limit=20)
            assert page["total"] == len(title_counts) and page["total_sources"] == len(expected)
            assert len(page["items"]) == min(20, len(title_counts) - page_number * 20)
            for group in page["items"]:
                title = group["title"]
                assert title not in seen_titles and group["source_count"] == title_counts[title]
                assert group["active_count"] == title_counts[title] and group["deleted_count"] == 0
                seen_titles.add(title)
                groups.append(group)
                seen_members = set()
                member_order = []
                for offset in range(0, title_counts[title], 5):
                    members = service.source_group_items(title=title, state="active", offset=offset, limit=5)
                    assert members["total"] == title_counts[title]
                    for member in members["items"]:
                        assert member["title"] == title and member["id"] not in seen_members
                        assert member["version"] == 1 and len(member["excerpt"]) <= 240
                        assert "content" not in member
                        seen_members.add(member["id"])
                        member_order.append((member["updated_at"], member["id"]))
                assert seen_members == expected_members[title], "Member pagination omitted or duplicated a Source."
                ordered_members = sorted(member_order, key=lambda member: member[1])
                ordered_members.sort(key=lambda member: member[0], reverse=True)
                assert member_order == ordered_members, "Member pages are not globally ordered."
                member_ids.update(seen_members)
        assert service.source_groups(q="", state="active", offset=page_count * 20, limit=20)["items"] == []
    assert seen_titles == set(title_counts) and len(member_ids) == len(expected)
    ordered = sorted(groups, key=lambda item: item["title"])
    ordered.sort(key=lambda item: item["latest_updated_at"], reverse=True)
    assert groups == ordered, "Groups are not globally ordered."
    return {"sources": len(expected), "title_groups": len(title_counts),
        "multi_source_groups": sum(count > 1 for count in title_counts.values()),
        "largest_group": max(title_counts.values(), default=0), "page_size": 20,
        "pages_checked": page_count, "members_verified": len(member_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "知乎")
    args = parser.parse_args()
    corpus = portable_path(PROJECT_ROOT, args.corpus.absolute())
    if not corpus.is_dir():
        parser.error("The corpus must be an existing directory inside the project.")
    evidence_parent = PROJECT_ROOT / ".cache/source-group-corpus"
    if evidence_parent.is_relative_to(corpus):
        parser.error("The corpus cannot contain the acceptance output directory.")
    evidence = evidence_parent / uuid4().hex
    evidence.mkdir(parents=True)
    report = {"status": "running", "real_model_calls": 0, "formal_instances_accessed": False,
              "report_contains_private_content": False, "evidence": str(evidence)}
    database, before = None, None
    try:
        before = fingerprint(corpus)
        raw, expected = read_corpus(corpus)
        batch = parse_markdown_document(raw)
        assert expected and len(expected) == sum(isinstance(entry, ParsedZhihuItem) for entry in batch.entries)
        database_path = evidence / "memory.db"
        database_url = f"sqlite:///{database_path.as_posix()}"
        upgrade_database(database_url)
        database = Database(database_url)
        database.initialize()
        importer = ImportService(database, RLock())
        preview = importer.run(batch.entries, dry_run=True)
        assert preview.would_create == len(expected) and preview.invalid == preview.failed == 0
        assert source_snapshot(database) == {}, "Preview wrote Sources."
        imported = importer.run(batch.entries)
        assert imported.created == len(expected) and imported.invalid == imported.failed == 0
        baseline = source_snapshot(database)
        for item in imported.items:
            if item.status == "created":
                source = baseline[item.source_id]
                assert source["version"] == 1 and source["deleted_at"] is None
                assert all(source[key] == expected[item.index][key]
                           for key in ("title", "author", "url", "body_sha256"))
        report["corpus"] = check_groups(database, expected, imported)
        assert source_snapshot(database) == baseline, "Read-only queries changed Sources or source text."
        report["zero_side_effect_table_counts"] = zero_side_effect_counts(database, len(expected))
        report.update(status="passed", preview_sources=preview.would_create,
                      source_versions_unchanged=True, source_body_hashes_match_original=True)
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__)
    finally:
        if database is not None:
            database.dispose()
        if before is not None:
            try:
                after = fingerprint(corpus)
                report.update(input_before=before, input_after=after, input_files_unchanged=before == after)
                if before != after:
                    report["status"] = "failed"
            except Exception as error:
                report.update(status="failed", input_before=before, input_files_unchanged=False,
                              final_input_check_error_type=type(error).__name__)
        (evidence / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "corpus": report.get("corpus"),
                      "report": str(evidence / "report.json")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
