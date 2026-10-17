"""Independent sorting oracle over authored, controlled SQLite seed records."""

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlencode

from source_groups_workflow import GROUPS

PREFIX = "排序便携验收"
FIELDS = ("title", "source_count", "source_type", "updated_at")


def source_snapshot(database: Path) -> str:
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        records = [dict(row) for row in connection.execute("SELECT * FROM sources ORDER BY id")]
        assert len(records) == 67
        for table in ("source_origins", "knowledge", "processing_runs", "rag_index_generations", "rag_note_index_states", "rag_index_jobs"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    return hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def seed_sorting(app, database: Path) -> list[dict]:
    titles = [f"{PREFIX} Alpha", f"{PREFIX} alpha", f"{PREFIX} Zulu"] + [f"{PREFIX} {index:02d}" for index in range(24)]
    records = []
    types = ("Zulu", "alpha", "alpha,legacy", "bravo")
    for index, title in enumerate(titles):
        for member in range(1 + index % 4):
            source_type = types[index % 4] if member == 0 else "zz-extra"
            payload = {"title": title, "source_type": source_type, "author": f"合成作者{index}-{member}",
                       "content": f"仅用于排序验收的独立资料 {index}-{member}。"}
            row = app.request("POST", "/api/v1/sources", payload)
            assert row["title"] == title and row["source_type"] == source_type
            row["updated_at"] = f"2030-01-{1 + index % 5:02d}T00:00:00.000000+00:00"
            records.append(row)
    # The deleted smallest type must not affect the normal-state MIN(type).
    archived = app.request("POST", "/api/v1/sources", {"title": titles[0], "source_type": "00-deleted",
        "author": "合成回收站作者", "content": "此记录只用于验证筛选后的可见类型排序。"})
    app.request("DELETE", f"/api/v1/sources/{archived['id']}?expected_version=1")
    archived = app.request("GET", f"/api/v1/sources/{archived['id']}?include_deleted=true")
    archived["updated_at"] = "2030-01-01T00:00:00.000000+00:00"
    records.append(archived)
    assert len(records) == 67
    # Only the test-owned .cache database is changed; this is fixture initialization.
    assert ".cache" in database.parts
    with sqlite3.connect(database) as connection:
        connection.executemany("UPDATE sources SET updated_at = ? WHERE id = ?",
                               [(row["updated_at"], row["id"]) for row in records])
    return records


def expected_groups(records: list[dict], field: str, order: str, *, state="active") -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        if state == "active" and record["deleted_at"] is not None:
            continue
        if state == "deleted" and record["deleted_at"] is None:
            continue
        grouped[record["title"]].append(record)
    values = [{"title": title, "source_count": len(items),
               "source_type": min(item["source_type"] for item in items),
               "source_types": sorted({item["source_type"] for item in items}),
               "updated_at": max(item["updated_at"] for item in items)} for title, items in grouped.items()]
    # Stable primary sorting preserves title ascending for every non-title tie.
    return sorted(sorted(values, key=lambda value: value["title"]),
                  key=lambda value: value[field], reverse=order == "desc")


def check_sort_api(app, records: list[dict]) -> list[dict]:
    checks = []
    for field in FIELDS:
        for order in ("asc", "desc"):
            expected = expected_groups(records, field, order)
            query = {"q": PREFIX, "state": "active", "limit": 100, "sort_by": field, "order": order}
            response = app.request("GET", GROUPS + "?" + urlencode(query))
            assert response["total"] == 27 and response["total_sources"] == 66
            assert [item["title"] for item in response["items"]] == [item["title"] for item in expected]
            for actual, desired in zip(response["items"], expected):
                assert actual["source_count"] == desired["source_count"]
                assert actual["source_types"] == desired["source_types"]
                assert actual["latest_updated_at"] == desired["updated_at"]
            second = app.request("GET", GROUPS + "?" + urlencode({**query, "offset": 20, "limit": 20}))
            assert [item["title"] for item in second["items"]] == [item["title"] for item in expected[20:]]
            checks.append({"sort_by": field, "order": order, "global_and_page_order": True, "title_ties": True})
    all_types = app.request("GET", GROUPS + "?" + urlencode({"state": "all", "sort_by": "source_type", "order": "asc", "limit": 100}))
    assert all_types["total_sources"] == 67
    assert [item["title"] for item in all_types["items"]] == [item["title"] for item in expected_groups(records, "source_type", "asc", state="all")]
    return checks
