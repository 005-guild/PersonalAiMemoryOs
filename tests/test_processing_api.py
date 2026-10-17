"""Public draft/adoption behavior, isolated from real models and storage."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest
from sqlalchemy import func, select

from app.agents.errors import AIError
from app.config import Settings
from app.main import create_app
from app.models import Knowledge, SyncOperation, SyncState

RAW = "索引会提高查询效率，但也会带来维护成本。"
GENERATED = {
    "title": "索引的收益与成本", "summary": "原文讨论索引的查询收益和维护成本。", "category": "数据库",
    "tags": ["数据库"], "concepts": ["索引"], "key_points": ["索引有查询收益，也有维护成本。"],
    "opinions": [{"statement": "索引需要权衡收益与成本。", "evidence": RAW,
                  "analysis": "可结合实际查询需求理解原文描述的权衡。"}],
}


class FakeModel:
    def __init__(self):
        self.calls = 0
        self.reply = json.dumps(GENERATED, ensure_ascii=False)
        self.error = None
        self.started = self.release = None

    async def generate(self, resolved, system_prompt, user_prompt):
        self.calls += 1
        assert json.loads(user_prompt)["content"]
        if self.started is not None:
            self.started.set()
            assert await asyncio.to_thread(self.release.wait, 5)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.reply, usage={"input_tokens": 25, "output_tokens": 40, "total_tokens": 65})


@pytest.fixture
def ai_app(settings: Settings, isolated_project: Path):
    profile_file = isolated_project / "providers.yml"
    profile_file.write_text(
        "schema_version: 1\ndefault_profile: test\nprofiles:\n  test:\n"
        "    enabled: true\n    protocol: openai_chat\n    base_url: https://example.invalid/v1\n"
        "    model: test-model\n    api_key_ref: test\n",
        encoding="utf-8",
    )
    model = FakeModel()
    configured = settings.model_copy(update={
        "ai_enabled": True, "ai_config_file": str(profile_file),
        "ai_keys": {"test": SecretStr("private-model-secret")},
    })
    app = create_app(configured, model_client=model)
    with TestClient(app) as client:
        yield client, app, model


def source(client, content=RAW):
    response = client.post("/api/v1/sources", json={"title": "原始资料", "content": content})
    assert response.status_code == 201
    return response.json()


def generate(client, record, **extra):
    return client.post("/api/v1/processing/runs", json={
        "source_id": record["id"], "expected_source_version": record["version"], **extra,
    })


def test_configured_profiles_and_draft_have_no_knowledge_or_file_side_effects(ai_app):
    client, app, model = ai_app
    profiles = client.get("/api/v1/ai/profiles")
    assert profiles.status_code == 200
    assert profiles.json()["default_profile"] == "test"
    assert profiles.json()["items"][0]["configured"] is True
    assert "private-model-secret" not in profiles.text
    record = source(client)
    response = generate(client, record)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["status"] == "ready" and run["source_stale"] is False
    assert run["profile_id"] == "test" and run["result"]["opinions"][0]["evidence"] == RAW
    assert run["proposal"]["source_id"] == record["id"]
    assert len(run["config_fingerprint"]) == len(run["prompt_hash"]) == 64
    assert model.calls == 1
    with app.state.database.session() as session:
        for table in (Knowledge, SyncState, SyncOperation):
            assert session.scalar(select(func.count()).select_from(table)) == 0
    assert not app.state.settings.knowledge_path.exists()
    assert "private-model-secret" not in response.text


def test_adoption_creates_once_and_exports_through_existing_sync(ai_app):
    client, _, model = ai_app
    run = generate(client, source(client)).json()
    request = {"expected_version": run["version"]}
    first = client.post(f"/api/v1/processing/runs/{run['id']}/adopt", json=request)
    assert first.status_code == 201, first.text
    adopted = first.json()
    assert adopted["already_adopted"] is False
    note = adopted["knowledge"]
    assert note["sync_status"] == "pending"
    assert "AI 分析：" in note["body"]
    repeat = client.post(f"/api/v1/processing/runs/{run['id']}/adopt", json=request)
    assert repeat.status_code == 200
    assert repeat.json()["already_adopted"] is True
    assert repeat.json()["knowledge"]["id"] == note["id"]
    assert client.get("/api/v1/knowledge").json()["total"] == 1
    assert model.calls == 1
    assert client.post("/api/v1/sync/run").status_code == 200
    assert client.get(f"/api/v1/knowledge/{note['id']}").json()["sync_status"] == "synced"


def test_adoption_retry_does_not_restore_deleted_note(ai_app):
    client, _, _ = ai_app
    run = generate(client, source(client)).json()
    target = f"/api/v1/processing/runs/{run['id']}/adopt"
    note = client.post(target, json={"expected_version": run["version"]}).json()["knowledge"]
    deleted = client.delete(f"/api/v1/knowledge/{note['id']}?expected_version={note['version']}")
    assert deleted.status_code == 200
    repeat = client.post(target, json={"expected_version": run["version"]})
    assert repeat.status_code == 200 and repeat.json()["knowledge"]["deleted"] is True
    assert client.get("/api/v1/knowledge").json()["total"] == 0
    assert client.get("/api/v1/knowledge?include_deleted=true").json()["total"] == 1


@pytest.mark.parametrize("change", ["edit", "delete"])
def test_source_changes_preserve_draft_but_block_adoption(ai_app, change):
    client, _, _ = ai_app
    record = source(client)
    run = generate(client, record).json()
    if change == "edit":
        client.patch(f"/api/v1/sources/{record['id']}", json={"expected_version": record["version"], "content": "新版原文"})
    else:
        client.delete(f"/api/v1/sources/{record['id']}?expected_version={record['version']}")
    current = client.get(f"/api/v1/processing/runs/{run['id']}").json()
    assert current["source_stale"] is True and current["status"] == "ready"
    assert current["source_snapshot"]["content"] == RAW
    assert client.post(f"/api/v1/processing/runs/{run['id']}/adopt", json={"expected_version": run["version"]}).status_code == 409
    assert client.get("/api/v1/knowledge").json()["total"] == 0


@pytest.mark.parametrize("status,code", [(502, "ai_upstream_error"), (504, "ai_timeout")])
def test_model_failure_returns_safe_persisted_run_id(ai_app, status, code):
    client, _, model = ai_app
    model.error = AIError(status, code)
    response = generate(client, source(client))
    assert response.status_code == status, response.text
    run_id = response.json()["detail"]["run_id"]
    run = client.get(f"/api/v1/processing/runs/{run_id}").json()
    assert run["status"] == "failed" and run["error_code"] == code
    assert run["result"] is None and run["proposal"] is None
    assert client.get("/api/v1/knowledge").json()["total"] == 0
    assert "private-model-secret" not in response.text


@pytest.mark.parametrize("reply", ["not JSON", json.dumps({**GENERATED, "opinions": [{"statement": "观点", "evidence": "伪造证据", "analysis": "分析"}]})])
def test_invalid_result_is_not_available_for_adoption(ai_app, reply):
    client, _, model = ai_app
    model.reply = reply
    response = generate(client, source(client))
    assert response.status_code == 502
    run_id = response.json()["detail"]["run_id"]
    run = client.get(f"/api/v1/processing/runs/{run_id}").json()
    assert run["status"] == "failed"
    assert client.post(f"/api/v1/processing/runs/{run_id}/adopt", json={"expected_version": run["version"]}).status_code == 409


def test_waiting_model_does_not_hold_sync_lock_and_second_generation_is_busy(ai_app):
    client, _, model = ai_app
    record = source(client)
    model.started, model.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(generate, client, record)
        try:
            assert model.started.wait(3)
            assert client.get("/health").status_code == 200
            assert client.get("/api/v1/processing/runs?status=running").json()["total"] == 1
            assert generate(client, record).status_code == 429
            assert client.post("/api/v1/sync/run").status_code == 200
            assert client.patch(f"/api/v1/sources/{record['id']}", json={"expected_version": record["version"], "title": "等待期间编辑"}).status_code == 200
        finally:
            model.release.set()
        response = pending.result(timeout=5)
    assert response.status_code == 201 and response.json()["source_stale"] is True


def test_run_list_pagination_filter_and_detail(ai_app):
    client, _, _ = ai_app
    record = source(client)
    one, two = generate(client, record).json(), generate(client, record).json()
    page = client.get(f"/api/v1/processing/runs?source_id={record['id']}&status=ready&profile_id=test&limit=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert "source_snapshot" not in page["items"][0] and "result" not in page["items"][0]
    second = client.get("/api/v1/processing/runs?offset=1&limit=1").json()
    assert second["items"][0]["id"] != page["items"][0]["id"]
    assert client.get(f"/api/v1/processing/runs/{one['id']}").json()["result"] == one["result"]
    assert one["id"] != two["id"]


@pytest.mark.parametrize("content", [" ", "x" * 20001])
def test_invalid_source_does_not_call_model(ai_app, content):
    client, _, model = ai_app
    assert generate(client, source(client, content)).status_code == 422
    assert model.calls == 0


def test_stale_source_and_unknown_profile(ai_app):
    client, _, model = ai_app
    record = source(client)
    assert generate(client, record, profile_id="missing").status_code == 422
    record["version"] += 1
    assert generate(client, record).status_code == 409
    assert model.calls == 0


def test_disabled_ai_preserves_existing_health_and_crud(client):
    assert client.get("/health").status_code == 200
    response = generate(client, source(client))
    assert response.status_code == 503
    assert client.get("/api/v1/processing/runs").json()["total"] == 0


def test_openapi_exposes_new_contracts(ai_app, project_version):
    client, _, _ = ai_app
    spec = client.get("/openapi.json").json()
    assert spec["info"]["version"] == project_version
    for path in ("/api/v1/ai/profiles", "/api/v1/processing/runs", "/api/v1/processing/runs/{run_id}/adopt"):
        assert path in spec["paths"]
    assert "ProcessingRequest" in spec["components"]["schemas"]
