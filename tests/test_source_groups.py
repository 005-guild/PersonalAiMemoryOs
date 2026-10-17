"""Full-set title grouping and bounded, read-only member pagination."""

from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.models import ProcessingRun, Source, SourceOrigin

GROUPS = "/api/v1/ui/source-groups"
MEMBERS = GROUPS + "/items"


def add_sources(client, *records):
    ids = []
    with client.app.state.database.session() as session:
        for values in records:
            record = Source(id=str(uuid4()), title="共同标题", source_type="manual", content="正文")
            for key, value in values.items():
                setattr(record, key, value)
            session.add(record)
            ids.append(record.id)
        session.commit()
    return ids


def test_empty_groups_and_members_preserve_pagination_metadata(client):
    assert client.get(GROUPS).json() == {
        "items": [], "total": 0, "total_sources": 0, "offset": 0, "limit": 20,
    }
    assert client.get(MEMBERS, params={"title": "不存在"}).json() == {
        "items": [], "total": 0, "offset": 0, "limit": 5,
    }


def test_title_group_is_global_before_pagination_not_flat_page_merging(client):
    records = [{"title": "共同标题", "updated_at": f"2026-01-{day:02d}T00:00:00+00:00"}
               for day in (1, 8, 16, 24)]
    records += [{"title": f"其他标题{index:02d}",
                 "updated_at": f"2026-01-{index + 2:02d}T00:00:00+00:00"}
                for index in range(25)]
    add_sources(client, *records)
    all_groups = []
    for offset in (0, 10, 20):
        page = client.get(GROUPS, params={"offset": offset, "limit": 10}).json()
        assert page["total"] == 26 and page["total_sources"] == 29
        assert page["offset"] == offset and page["limit"] == 10
        all_groups.extend(page["items"])
    assert len(all_groups) == len({item["title"] for item in all_groups}) == 26
    group = next(item for item in all_groups if item["title"] == "共同标题")
    assert group["source_count"] == group["active_count"] == 4 and group["deleted_count"] == 0
    members = []
    for offset in (0, 2):
        page = client.get(MEMBERS, params={"title": "共同标题", "offset": offset, "limit": 2}).json()
        assert page["total"] == 4
        members.extend(page["items"])
    assert len({item["id"] for item in members}) == 4
    assert [item["updated_at"] for item in members] == sorted(
        (item["updated_at"] for item in members), reverse=True,
    )


def test_group_order_and_member_order_are_stable_with_timestamp_ties(client):
    stamp = "2026-01-01T00:00:00+00:00"
    ids = add_sources(client, {"title": "乙", "updated_at": stamp},
                      {"title": "甲", "updated_at": stamp},
                      {"title": "乙", "updated_at": stamp})
    first = client.get(GROUPS, params={"limit": 1}).json()
    second = client.get(GROUPS, params={"offset": 1, "limit": 1}).json()
    assert [first["items"][0]["title"], second["items"][0]["title"]] == sorted(["乙", "甲"])
    members = client.get(MEMBERS, params={"title": "乙"}).json()["items"]
    assert [item["id"] for item in members] == sorted([ids[0], ids[2]])


def test_grouping_and_membership_use_exact_titles_without_case_or_space_normalization(client):
    titles = ["ABC", "abc", "中文", "中文 "]
    ids = add_sources(client, *[{"title": title} for title in titles])
    assert client.get(GROUPS).json()["total"] == 4
    for title, expected_id in zip(titles, ids, strict=True):
        page = client.get(MEMBERS, params={"title": title}).json()
        assert page["total"] == 1 and page["items"][0]["id"] == expected_id


def test_source_types_preserve_commas_without_string_aggregation_splitting(client):
    add_sources(client, {"source_type": "custom,with,commas"}, {"source_type": "custom,with,commas"},
                {"source_type": "custom"})
    group = client.get(GROUPS).json()["items"][0]
    assert group["source_count"] == 3
    assert group["source_types"] == ["custom", "custom,with,commas"]


@pytest.mark.parametrize("query", ["%", "_", "/", "中文", "' OR 1=1 --"])
def test_group_query_literal_contains_and_member_title_exact_match(client, query):
    title = f"之前{query}之后"
    add_sources(client, {"title": title}, {"title": title}, {"title": "普通标题"})
    page = client.get(GROUPS, params={"q": query}).json()
    assert page["total"] == 1 and page["total_sources"] == 2
    assert page["items"][0]["title"] == title
    assert client.get(MEMBERS, params={"title": query}).json()["total"] == 0
    assert client.get(MEMBERS, params={"title": title}).json()["total"] == 2


@pytest.mark.parametrize("state,total,total_sources,visible_count,active_count,deleted_count,types", [
    ("active", 2, 3, 2, 2, 0, ["manual", "zhihu"]),
    ("deleted", 2, 2, 1, 0, 1, ["web"]),
    ("all", 3, 5, 3, 2, 1, ["manual", "web", "zhihu"]),
])
def test_state_is_applied_before_group_counts_types_latest_and_totals(
    client, state, total, total_sources, visible_count, active_count, deleted_count, types,
):
    old, latest = "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"
    add_sources(client,
        {"title": "混合", "source_type": "manual", "updated_at": old},
        {"title": "混合", "source_type": "zhihu", "updated_at": old},
        {"title": "混合", "source_type": "web", "updated_at": latest, "deleted_at": latest},
        {"title": "只有正常"}, {"title": "只有回收站", "deleted_at": latest},
    )
    page = client.get(GROUPS, params={"state": state}).json()
    assert (page["total"], page["total_sources"]) == (total, total_sources)
    group = next(item for item in page["items"] if item["title"] == "混合")
    assert group["source_count"] == visible_count
    assert group["active_count"] == active_count and group["deleted_count"] == deleted_count
    assert group["source_types"] == types
    assert group["latest_updated_at"] == (old if state == "active" else latest)
    assert client.get(MEMBERS, params={"title": "混合", "state": state}).json()["total"] == visible_count
    filtered = client.get(GROUPS, params={"state": state, "q": "混合"}).json()
    assert filtered["total"] == 1 and filtered["total_sources"] == visible_count


@pytest.mark.parametrize("endpoint,query", [
    (GROUPS, {"state": "invalid"}), (GROUPS, {"offset": -1}), (GROUPS, {"limit": 0}),
    (GROUPS, {"limit": 101}), (GROUPS, {"q": "x" * 501}),
    (MEMBERS, {}), (MEMBERS, {"title": ""}), (MEMBERS, {"title": "x" * 501}),
    (MEMBERS, {"title": "x", "state": "invalid"}), (MEMBERS, {"title": "x", "offset": -1}),
    (MEMBERS, {"title": "x", "limit": 0}), (MEMBERS, {"title": "x", "limit": 101}),
])
def test_query_boundaries_reject_invalid_values(client, endpoint, query):
    assert client.get(endpoint, params=query).status_code == 422


def test_upper_limit_and_offset_past_end_return_accurate_totals(client):
    add_sources(client, {"title": "一组"}, {"title": "一组"})
    page = client.get(GROUPS, params={"offset": 999, "limit": 100}).json()
    assert page == {"items": [], "total": 1, "total_sources": 2, "offset": 999, "limit": 100}
    page = client.get(MEMBERS, params={"title": "一组", "offset": 999, "limit": 100}).json()
    assert page == {"items": [], "total": 2, "offset": 999, "limit": 100}


def test_large_bodies_are_not_selected_by_grouping_and_members_fetch_only_excerpt(client):
    content = "中文正文" * 250_000
    ids = add_sources(client, {"content": content})
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        groups = client.get(GROUPS)
        assert groups.status_code == 200
        assert all("sources.content" not in statement for statement in statements)
        statements.clear()
        members = client.get(MEMBERS, params={"title": "共同标题"})
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    item = members.json()["items"][0]
    assert item["excerpt"] == content[:240] and "content" not in item
    content_queries = [statement for statement in statements if "sources.content" in statement]
    assert len(content_queries) == 1 and "substr(sources.content" in content_queries[0]
    assert len(members.content) < 2000 and len(groups.content) < 1000
    assert client.get("/api/v1/sources/" + ids[0]).json()["content"] == content


def test_gets_do_not_merge_sources_change_versions_origins_or_processing(client):
    ids = add_sources(client, {"author": "作者甲", "content": "回答甲"},
                      {"author": "作者乙", "content": "回答乙"})
    before = [client.get("/api/v1/sources/" + source_id).json() for source_id in ids]
    for state in ("active", "all", "deleted"):
        assert client.get(GROUPS, params={"state": state}).status_code == 200
        assert client.get(MEMBERS, params={"title": "共同标题", "state": state}).status_code == 200
    assert [client.get("/api/v1/sources/" + source_id).json() for source_id in ids] == before
    with client.app.state.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 2
        assert session.scalar(select(func.count()).select_from(SourceOrigin)) == 0
        assert session.scalar(select(func.count()).select_from(ProcessingRun)) == 0
    assert client.get("/api/v1/ui/sources").json()["total"] == 2
    assert client.get("/api/v1/sources").json()["total"] == 2


def test_edit_delete_restore_naturally_regroup_without_touching_other_answers(client):
    ids = add_sources(client, {}, {})
    response = client.patch("/api/v1/sources/" + ids[0], json={"expected_version": 1, "title": "新标题"})
    assert response.status_code == 200
    assert client.get(GROUPS).json()["total"] == 2
    assert client.get(MEMBERS, params={"title": "共同标题"}).json()["total"] == 1
    assert client.delete("/api/v1/sources/" + ids[1], params={"expected_version": 1}).status_code == 200
    assert client.get(GROUPS).json()["total"] == 1
    assert client.get(GROUPS, params={"state": "all"}).json()["total"] == 2
    assert client.post("/api/v1/sources/" + ids[1] + "/restore", json={"expected_version": 2}).status_code == 200
    assert client.get(GROUPS).json()["total"] == 2
    assert client.get(MEMBERS, params={"title": "共同标题"}).json()["items"][0]["id"] == ids[1]
