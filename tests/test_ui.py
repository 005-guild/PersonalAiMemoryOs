"""Workbench projections remain bounded, filterable and read-only."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.models import ProcessingRun, SyncConflict, SyncState


def source(client: TestClient, **values) -> dict:
    response = client.post("/api/v1/sources", json={"title": "资料", **values})
    assert response.status_code == 201, response.text
    return response.json()


def note(client: TestClient, **values) -> dict:
    response = client.post("/api/v1/knowledge", json={"title": "笔记", **values})
    assert response.status_code == 201, response.text
    return response.json()


def test_overview_counts_only_active_records_ready_drafts_and_open_conflicts(client):
    assert client.get("/api/v1/ui/overview").json() == {
        "active_sources": 0, "active_knowledge": 0, "ready_drafts": 0, "open_conflicts": 0,
    }
    active_source = source(client)
    deleted_source = source(client)
    active_note = note(client, source_id=active_source["id"])
    deleted_note = note(client)
    client.delete(f"/api/v1/sources/{deleted_source['id']}?expected_version=1")
    client.delete(f"/api/v1/knowledge/{deleted_note['id']}?expected_version=1")
    with client.app.state.database.session() as session:
        for status in ("ready", "failed", "adopted", "running", "interrupted"):
            session.add(ProcessingRun(
                source_id=active_source["id"], source_version=1, source_snapshot={},
                input_hash="a" * 64, profile_id="test", protocol="openai_chat", model="test",
                config_fingerprint="b" * 64, prompt_version="v1", prompt_hash="c" * 64,
                output_schema_version=1, status=status,
            ))
        for status in ("open", "resolved", "superseded"):
            session.add(SyncConflict(knowledge_id=active_note["id"], db_snapshot={},
                                     db_version=1, reason="both_changed", status=status))
        session.commit()
    assert client.get("/api/v1/ui/overview").json() == {
        "active_sources": 1, "active_knowledge": 1, "ready_drafts": 1, "open_conflicts": 1,
    }


@pytest.mark.parametrize("collection,create", [("sources", source), ("knowledge", note)])
def test_summary_paging_and_trash_are_independent_of_existing_api(client, collection, create):
    first = create(client, title="甲")
    create(client, title="乙")
    create(client, title="丙")
    page = client.get(f"/api/v1/ui/{collection}", params={"offset": 1, "limit": 1}).json()
    assert page["total"] == 3 and page["offset"] == 1 and page["limit"] == 1
    assert len(page["items"]) == 1
    assert client.delete(f"/api/v1/{collection}/{first['id']}?expected_version=1").status_code == 200
    active = client.get(f"/api/v1/ui/{collection}").json()
    trash = client.get(f"/api/v1/ui/{collection}?state=deleted").json()
    all_records = client.get(f"/api/v1/ui/{collection}?state=all").json()
    assert active["total"] == 2 and all_records["total"] == 3
    assert trash["total"] == 1 and trash["items"][0]["id"] == first["id"]
    assert trash["items"][0]["deleted_at"] is not None
    assert client.get(f"/api/v1/{collection}").json()["total"] == 2
    assert client.get(f"/api/v1/{collection}?include_deleted=true").json()["total"] == 3


@pytest.mark.parametrize("collection,create", [("sources", source), ("knowledge", note)])
@pytest.mark.parametrize("query", ["%", "_", "/", "中文", "' OR 1=1 --"])
def test_title_filter_uses_literal_contains_not_like_wildcards(client, collection, create, query):
    match = create(client, title=f"之前{query}之后")
    create(client, title="普通标题")
    response = client.get(f"/api/v1/ui/{collection}", params={"q": query})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == match["id"]


def test_source_summary_fetches_only_excerpt_and_detail_still_returns_entire_content(client):
    content = "中文正文" * 25_000
    record = source(client, content=content, author="作者", url="https://example.invalid/", source_type="zhihu")
    statements = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/v1/ui/sources")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    item = response.json()["items"][0]
    assert item["title"] == record["title"]
    assert item["excerpt"] == content[:240] and "content" not in item
    assert item["author"] == "作者" and item["source_type"] == "zhihu"
    projections = [statement.split("FROM")[0] for statement in statements if "sources.content" in statement]
    assert len(projections) == 1 and "substr(sources.content" in projections[0]
    assert client.get(f"/api/v1/sources/{record['id']}").json()["content"] == content


def test_note_summary_filters_source_and_projects_metadata_without_body(client):
    first_source = source(client, title="来源一")
    second_source = source(client, title="来源二")
    body, summary = "正文" * 50_000, "长摘要" * 10_000
    record = note(client, source_id=first_source["id"], body=body, summary=summary,
                  category="数据库", tags=["中文", "SQL"], concepts=["索引"])
    note(client, source_id=second_source["id"])
    note(client)
    with client.app.state.database.session() as session:
        state = session.get(SyncState, record["id"])
        state.path, state.status = "分类/移动后的笔记.md", "synced"
        session.commit()
    response = client.get("/api/v1/ui/knowledge", params={"source_id": first_source["id"]})
    item = response.json()["items"][0]
    assert response.json()["total"] == 1 and item["id"] == record["id"]
    assert item["title"] == record["title"]
    assert item["summary"] == summary[:240] and "body" not in item
    assert item["source_id"] == first_source["id"] and item["version"] == 1
    assert item["category"] == "数据库" and item["tags"] == ["中文", "SQL"]
    assert item["concepts"] == ["索引"] and item["deleted"] is False
    assert item["path"] == "分类/移动后的笔记.md" and item["sync_status"] == "synced"
    assert client.get("/api/v1/ui/knowledge", params={"source_id": str(uuid4())}).json()["total"] == 0
    assert client.get(f"/api/v1/knowledge/{record['id']}").json()["body"] == body


@pytest.mark.parametrize("query", [
    {"state": "invalid"}, {"offset": -1}, {"limit": 0}, {"limit": 101}, {"q": "长" * 501},
])
@pytest.mark.parametrize("collection", ["sources", "knowledge"])
def test_summary_query_validation(client, collection, query):
    assert client.get(f"/api/v1/ui/{collection}", params=query).status_code == 422


def test_knowledge_source_filter_is_a_uuid(client):
    assert client.get("/api/v1/ui/knowledge?source_id=invalid").status_code == 422


def test_summary_gets_never_change_record_version_or_sync_state(client):
    record = note(client)
    before = client.get(f"/api/v1/knowledge/{record['id']}").json()
    for endpoint in ("overview", "sources", "knowledge"):
        assert client.get(f"/api/v1/ui/{endpoint}").status_code == 200
    assert client.get(f"/api/v1/knowledge/{record['id']}").json() == before
