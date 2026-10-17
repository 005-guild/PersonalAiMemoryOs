"""RAG settings enforce the AI configuration token and non-sensitive errors."""

import asyncio
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from app.api.rag_settings import router
from app.api.rag_settings_schemas import RAGSettingsTest
from app.api.settings_security import ConfigurationNoStoreMiddleware, configuration_guard
from app.config import Settings
from app.services.rag_settings import RAGSettingsService
from app.services.rag_settings_state import RAGSettingsError
from app.vector.embedding import EmbeddingClient, EmbeddingReply

TOKEN = "synthetic-shared-configuration-token"


@pytest.fixture
def rig(isolated_project):
    root = isolated_project
    (root / "config").mkdir()
    (root / ".env").write_text("MEMORY_OS_AI_KEYS__DEMO=synthetic-secret\n", encoding="utf-8")
    (root / "config/embedding-providers.yml").write_text(
        "schema_version: 1\ndefault_profile: demo\nprofiles:\n  demo:\n    base_url: http://model.invalid/v1\n    model: demo\n    dimension: 3\n    api_key_ref: demo\n", encoding="utf-8")
    settings = Settings(runtime_root=root, _env_file=root / ".env", sync_enabled=False)
    service = RAGSettingsService(settings, csrf_token=TOKEN, environ={})
    app = FastAPI()
    app.state.ai_settings = SimpleNamespace(csrf_token=TOKEN)
    app.state.rag_settings = service
    app.state.configuration_guard = configuration_guard
    app.add_middleware(ConfigurationNoStoreMiddleware)
    app.include_router(router)
    with TestClient(app, base_url="http://127.0.0.1:18000") as client:
        yield root, service, client


def headers():
    return {"Origin": "http://127.0.0.1:18000", "X-Configuration-Token": TOKEN}


def test_api_uses_shared_token_safe_fields_and_no_cache(rig):
    root, _, client = rig
    response = client.get("/api/v1/settings/rag")
    value = response.json()
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert value["csrf_token"] == TOKEN and not value["desktop"]["restart_supported"]
    assert "synthetic-secret" not in response.text
    payload = {"expected_revision": value["revision"], "enabled": False, "qdrant_url": value["qdrant_url"],
               "default_profile": "demo", "profiles": value["profiles"]}
    assert client.put("/api/v1/settings/rag", json=payload).status_code == 403
    assert client.put("/api/v1/settings/rag", json=payload, headers=headers()).status_code == 200
    payload["profiles"][0]["extra_body"] = {"nested": {"api_key": "SENSITIVE_INVALID_VALUE"}}
    invalid = client.put("/api/v1/settings/rag", json=payload, headers=headers())
    assert invalid.status_code == 422 and "SENSITIVE_INVALID_VALUE" not in invalid.text
    assert client.get("/api/v1/settings/rag", headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert not (root / "data").exists()


@pytest.mark.parametrize("body", [
    '{"target":"qdrant","target":"embedding"}', '{"value":NaN}', 'null', '{',
])
def test_invalid_json_and_duplicates_fail_safely(rig, body):
    _, _, client = rig
    response = client.post("/api/v1/settings/rag/test", content=body, headers={**headers(), "Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_request_size_limit(rig):
    _, _, client = rig
    response = client.put("/api/v1/settings/rag", content=b" " * (1024 * 1024 + 1), headers={**headers(), "Content-Type": "application/json"})
    assert response.status_code == 413


def test_qdrant_test_only_gets_root_and_never_creates_collection(rig):
    root, service, client = rig
    calls = []
    def transport(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"version": "1.19.2"})
    service.probes.qdrant_transport = httpx.MockTransport(transport)
    response = client.post("/api/v1/settings/rag/test", json={"expected_revision": service.describe()["revision"], "target": "qdrant"}, headers=headers())
    assert response.status_code == 200
    assert response.json() == {"target": "qdrant", "status": "ok", "read_only": True}
    assert calls == [("GET", "/")]
    assert not (root / "data").exists() and not (root / "knowledge").exists()


def test_embedding_test_requires_confirmation_and_calls_exactly_once(rig):
    root, service, client = rig
    calls = []
    def transport(request):
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer synthetic-secret"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0]}], "usage": {"total_tokens": 4}})
    service.probes.embedding_client = EmbeddingClient(httpx.MockTransport(transport))
    payload = {"expected_revision": service.describe()["revision"], "target": "embedding"}
    assert client.post("/api/v1/settings/rag/test", json=payload, headers=headers()).status_code == 422
    assert calls == []
    response = client.post("/api/v1/settings/rag/test", json={**payload, "confirm_embedding": True}, headers=headers())
    assert response.status_code == 200
    assert response.json()["calls"] == 1 and response.json()["dimension"] == 3
    assert calls == [{"model": "demo", "input": ["知识库向量连接测试。"], "encoding_format": "float"}]
    assert not (root / "data").exists() and not (root / "knowledge").exists()


def test_embedding_failure_is_safe_and_never_retries(rig):
    _, service, client = rig
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(401, json={"detail": "synthetic-secret must never echo"})
    service.probes.embedding_client = EmbeddingClient(httpx.MockTransport(transport))
    response = client.post("/api/v1/settings/rag/test", json={"expected_revision": service.describe()["revision"], "target": "embedding", "confirm_embedding": True}, headers=headers())
    assert response.status_code == 502 and "synthetic-secret" not in response.text
    assert len(calls) == 1


def test_probe_busy_and_stale_revision_never_duplicate_calls(rig):
    _, service, _ = rig
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def embed(resolved, texts):
            calls.append(texts)
            started.set()
            await release.wait()
            return EmbeddingReply([[1, 2, 3]], {})
        service.probes.embedding_client = SimpleNamespace(embed=embed)
        payload = RAGSettingsTest(expected_revision=service.describe()["revision"], target="embedding", confirm_embedding=True)
        task = asyncio.create_task(service.probes.run(payload))
        await started.wait()
        with pytest.raises(RAGSettingsError, match="configuration_test_busy"):
            await service.probes.run(payload)
        release.set()
        await task
        stale = payload.model_copy(update={"expected_revision": "0" * 64})
        with pytest.raises(RAGSettingsError, match="configuration_changed"):
            await service.probes.run(stale)
        assert len(calls) == 1
    asyncio.run(scenario())


def test_cancellation_and_unexpected_failure_release_probe_lock(rig):
    _, service, _ = rig
    async def scenario():
        started = asyncio.Event()
        async def waiting(resolved, texts):
            started.set()
            await asyncio.Future()
        service.probes.embedding_client = SimpleNamespace(embed=waiting)
        payload = RAGSettingsTest(expected_revision=service.describe()["revision"], target="embedding", confirm_embedding=True)
        task = asyncio.create_task(service.probes.run(payload))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not service.probes._busy.locked()
        async def unexpected(resolved, texts):
            raise RuntimeError("synthetic-secret")
        service.probes.embedding_client = SimpleNamespace(embed=unexpected)
        with pytest.raises(RAGSettingsError, match="configuration_test_failed") as error:
            await service.probes.run(payload)
        assert "synthetic-secret" not in str(error.value)
        assert not service.probes._busy.locked()
    asyncio.run(scenario())


def test_probe_invalid_dimension_and_config_version_changes_are_explicit(rig):
    root, service, client = rig
    calls = []
    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2]}]})
    service.probes.embedding_client = EmbeddingClient(httpx.MockTransport(transport))
    payload = {"expected_revision": service.describe()["revision"], "target": "embedding", "confirm_embedding": True}
    response = client.post("/api/v1/settings/rag/test", json=payload, headers=headers())
    assert response.status_code == 502 and response.json()["detail"]["code"] == "embedding_response_invalid"
    assert len(calls) == 1
    with (root / ".env").open("a", encoding="utf-8") as stream:
        stream.write("# concurrent unrelated configuration edit\n")
    response = client.post("/api/v1/settings/rag/test", json=payload, headers=headers())
    assert response.status_code == 409 and len(calls) == 1
