"""Global group sorting remains stable, filtered, bounded and read-only."""

from collections import defaultdict

import pytest
from sqlalchemy import event, select

from app.models import Source
from app.repositories.ui import UIRepository
from app.services.ui import UIService
from test_source_groups import GROUPS, MEMBERS, add_sources

FIELDS = {"title", "source_count", "active_count", "deleted_count", "latest_updated_at", "source_types"}
SORTS = ["title", "source_count", "source_type", "updated_at"]


def records():
    def row(title, kind, day, deleted=False):
        stamp = f"2026-01-{day:02d}T00:00:00+00:00"
        return {"title": title, "source_type": kind, "updated_at": stamp,
                "deleted_at": stamp if deleted else None, "content": "不得载入的完整原文" * 1000}

    return [row("A%_/", "z", 1), row("A%_/", "b,comma", 2), row("A%_/", "a", 6, True),
            row("B", "b", 5), row("B", "c", 5), row("C%_/", "c", 3), row("C%_/", "zz", 2, True),
            row("D%_/", "b", 5), row("E", "a", 1), row("F", "d", 4), row("F", "d", 4),
            row("G", "b,comma", 2), row("H", "a", 1), row("OnlyTrash", "0", 7, True)]


def expected(records, sort_by, order, *, state="active", q=""):
    grouped = defaultdict(list)
    for record in records:
        if q not in record["title"]:
            continue
        if state != "all" and bool(record["deleted_at"]) != (state == "deleted"):
            continue
        grouped[record["title"]].append(record)
    items = [{"title": title, "source_count": len(rows),
              "active_count": sum(row["deleted_at"] is None for row in rows),
              "deleted_count": sum(row["deleted_at"] is not None for row in rows),
              "latest_updated_at": max(row["updated_at"] for row in rows),
              "source_types": sorted({row["source_type"] for row in rows})}
             for title, rows in grouped.items()]
    key = {"title": lambda item: item["title"], "source_count": lambda item: item["source_count"],
           "updated_at": lambda item: item["latest_updated_at"],
           "source_type": lambda item: item["source_types"][0]}[sort_by]
    items.sort(key=lambda item: item["title"])
    items.sort(key=key, reverse=order == "desc")
    return items


@pytest.mark.parametrize("sort_by", SORTS)
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_all_eight_combinations_sort_all_groups_before_paging_with_stable_ties(client, sort_by, order):
    seed = records()
    add_sources(client, *seed)
    wanted = expected(seed, sort_by, order)
    collected = []
    for offset in range(0, len(wanted), 2):
        response = client.get(GROUPS, params={"sort_by": sort_by, "order": order,
                                             "offset": offset, "limit": 2})
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == len(wanted)
        assert page["total_sources"] == sum(item["source_count"] for item in wanted)
        assert page["items"] == wanted[offset:offset + 2]
        assert all(set(item) == FIELDS for item in page["items"])
        collected.extend(page["items"])
    assert collected == wanted and len({item["title"] for item in collected}) == len(wanted)


@pytest.mark.parametrize("sort_by", SORTS)
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("state", ["active", "deleted", "all"])
def test_filters_precede_sort_keys_counts_and_global_page_order(client, sort_by, order, state):
    seed = records()
    add_sources(client, *seed)
    query = "%_/"
    wanted = expected(seed, sort_by, order, state=state, q=query)
    response = client.get(GROUPS, params={"sort_by": sort_by, "order": order, "state": state,
                                         "q": query, "offset": 1, "limit": 1})
    assert response.status_code == 200
    page = response.json()
    assert page["items"] == wanted[1:2]
    assert page["total"] == len(wanted)
    assert page["total_sources"] == sum(item["source_count"] for item in wanted)


def test_visible_type_minimum_is_scalar_and_preserves_comma_types(client):
    add_sources(client, {"title": "mixed", "source_type": "z"},
                {"title": "mixed", "source_type": "a", "deleted_at": "2026-01-01T00:00:00+00:00"},
                {"title": "plain", "source_type": "m"},
                {"title": "comma", "source_type": "custom,with,commas"})
    active = client.get(GROUPS, params={"sort_by": "source_type", "order": "asc"}).json()["items"]
    visible_all = client.get(GROUPS, params={"sort_by": "source_type", "order": "asc", "state": "all"}).json()["items"]
    assert [item["title"] for item in active] == ["comma", "plain", "mixed"]
    assert [item["title"] for item in visible_all] == ["mixed", "comma", "plain"]
    assert active[0]["source_types"] == ["custom,with,commas"]


def test_source_count_sort_is_numeric_rather_than_lexicographic(client):
    add_sources(client, *([{"title": "two"}] * 2 + [{"title": "ten"}] * 10))
    ascending = client.get(GROUPS, params={"sort_by": "source_count", "order": "asc"}).json()["items"]
    descending = client.get(GROUPS, params={"sort_by": "source_count", "order": "desc"}).json()["items"]
    assert [(item["title"], item["source_count"]) for item in ascending] == [("two", 2), ("ten", 10)]
    assert [(item["title"], item["source_count"]) for item in descending] == [("ten", 10), ("two", 2)]


@pytest.mark.parametrize("order", ["asc", "desc"])
def test_unicode_title_sort_uses_database_character_order_without_normalizing_sources(client, order):
    titles = ["阿", "中文", "资料2", "资料10", "A", "a", "Z", "z", "😀", "🧠"]
    add_sources(client, *[{"title": title, "content": "保持完整原文" + title} for title in titles])
    database = client.app.state.database

    def snapshot():
        with database.session() as session:
            return [tuple(row) for row in session.execute(select(
                Source.id, Source.title, Source.version, Source.updated_at, Source.content,
            ).order_by(Source.id))]

    before, collected = snapshot(), []
    for offset in range(0, len(titles), 3):
        response = client.get(GROUPS, params={"sort_by": "title", "order": order,
                                             "offset": offset, "limit": 3})
        assert response.status_code == 200
        page = response.json()
        assert page["total"] == page["total_sources"] == len(titles)
        collected.extend(item["title"] for item in page["items"])
    assert collected == sorted(titles, reverse=order == "desc")
    assert snapshot() == before


@pytest.mark.parametrize("query", [
    {"sort_by": "invalid"}, {"sort_by": "TITLE"}, {"sort_by": ""},
    {"sort_by": "title desc; DROP TABLE sources"}, {"order": "invalid"}, {"order": "ASC"},
    {"order": ""}, {"order": "desc; DROP TABLE sources"},
])
def test_sort_parameters_are_strict_literals(client, query):
    assert client.get(GROUPS, params=query).status_code == 422


def test_default_order_and_response_and_old_service_calls_are_unchanged(client):
    add_sources(client, *records())
    implicit = client.get(GROUPS).json()
    explicit = client.get(GROUPS, params={"sort_by": "updated_at", "order": "desc"}).json()
    assert implicit == explicit
    assert set(implicit) == {"items", "total", "total_sources", "offset", "limit"}
    with client.app.state.database.session() as session:
        assert UIService(session).source_groups(q="", state="active", offset=0, limit=20) == implicit
        items, total, total_sources = UIRepository(session).source_groups(
            q="", state="active", offset=0, limit=20,
        )
        assert items == implicit["items"] and total == implicit["total"]
        assert total_sources == implicit["total_sources"]


def test_sorting_reads_no_body_and_never_writes_or_changes_member_order(client):
    add_sources(client, *records())
    database = client.app.state.database
    with database.session() as session:
        before = [tuple(row) for row in session.execute(select(
            Source.id, Source.title, Source.version, Source.updated_at, Source.deleted_at, Source.content,
        ).order_by(Source.id))]
    before_members = client.get(MEMBERS, params={"title": "A%_/", "state": "all"}).json()
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(database.engine, "before_cursor_execute", capture)
    try:
        for sort_by in SORTS:
            for order in ("asc", "desc"):
                assert client.get(GROUPS, params={"sort_by": sort_by, "order": order}).status_code == 200
    finally:
        event.remove(database.engine, "before_cursor_execute", capture)
    assert statements and all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert all("sources.content" not in statement for statement in statements)
    assert client.get(MEMBERS, params={"title": "A%_/", "state": "all"}).json() == before_members
    with database.session() as session:
        after = [tuple(row) for row in session.execute(select(
            Source.id, Source.title, Source.version, Source.updated_at, Source.deleted_at, Source.content,
        ).order_by(Source.id))]
    assert before == after


def test_empty_and_out_of_range_pages_keep_original_wire_for_each_sort(client):
    for sort_by in SORTS:
        assert client.get(GROUPS, params={"sort_by": sort_by}).json() == {
            "items": [], "total": 0, "total_sources": 0, "offset": 0, "limit": 20,
        }
    add_sources(client, {"title": "only"})
    for sort_by in SORTS:
        page = client.get(GROUPS, params={"sort_by": sort_by, "order": "asc", "offset": 1000}).json()
        assert page == {"items": [], "total": 1, "total_sources": 1, "offset": 1000, "limit": 20}
