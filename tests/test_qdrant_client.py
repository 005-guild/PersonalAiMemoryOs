"""Qdrant REST compatibility, ownership gates, and failure isolation."""

import asyncio
import json

import httpx
import pytest

from app.vector.errors import RagError
from app.vector.qdrant import QdrantClient

OWNER = {"owner": "test-project", "generation_id": "test-generation"}


def collection(metadata=None, dimension=3, distance="Cosine"):
    return {"status": "ok", "result": {"config": {
        "metadata": OWNER if metadata is None else metadata,
        "params": {"vectors": {"size": dimension, "distance": distance}}}}}


def test_create_validate_upsert_query_delete_with_real_metadata_shape():
    calls = []
    exists = False
    def handler(request):
        nonlocal exists
        calls.append((request.method, str(request.url)))
        if request.url.path == "/":
            return httpx.Response(200, json={"version": "1.19.2"})
        if request.url.path == "/collections/test" and request.method == "GET":
            return httpx.Response(200, json=collection()) if exists else httpx.Response(404)
        if request.url.path == "/collections/test" and request.method == "PUT":
            body = json.loads(request.content)
            assert body == {"vectors": {"size": 3, "distance": "Cosine"}, "metadata": OWNER}
            exists = True
        elif request.url.path.endswith("/points/query"):
            body = json.loads(request.content)
            assert body == {"query": [1, 0, 0], "limit": 5, "with_payload": True}
            return httpx.Response(200, json={"status": "ok", "result": {"points": [
                {"id": "point-uuid", "score": 0.9, "payload": {"knowledge_id": "note"}}]}})
        elif request.url.path.endswith("/points"):
            assert request.url.params["wait"] == "true"
        elif request.url.path.endswith("/points/delete"):
            assert request.url.params["wait"] == "true"
            assert json.loads(request.content) == {"points": ["point-uuid"]}
        return httpx.Response(200, json={"status": "ok", "result": True})
    async def scenario():
        client = QdrantClient("http://localhost:6333", transport=httpx.MockTransport(handler))
        await client.ensure_collection("test", 3, OWNER)
        await client.upsert("test", [{"id": "point-uuid", "vector": [1, 0, 0], "payload": {}}])
        assert (await client.query("test", [1, 0, 0], 5))[0]["score"] == 0.9
        await client.delete_points("test", ["point-uuid"])
        await client.delete_collection("test", OWNER)
        await client.aclose()
    asyncio.run(scenario())
    assert calls[-1] == ("DELETE", "http://localhost:6333/collections/test")


@pytest.mark.parametrize("reply,code", [
    (collection(metadata={"owner": "foreign"}), "qdrant_collection_ownership_mismatch"),
    (collection(dimension=4), "qdrant_collection_schema_mismatch"),
    (collection(distance="Dot"), "qdrant_collection_schema_mismatch"),
    ({"result": {"config": {"metadata": OWNER, "params": {"vectors": {"named": {"size": 3}}}}}},
     "qdrant_collection_schema_mismatch"),
])
def test_foreign_or_incompatible_collection_is_never_modified(reply, code):
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"version": "1.19.2"} if request.url.path == "/" else reply)
    with pytest.raises(RagError, match=code):
        asyncio.run(QdrantClient("http://qdrant", httpx.MockTransport(handler)).ensure_collection("test", 3, OWNER))
    assert calls == ["GET", "GET"]


def test_missing_collection_no_create_and_unverified_mutation():
    def handler(request):
        return httpx.Response(200, json={"version": "1.19.2"}) if request.url.path == "/" else httpx.Response(404)
    client = QdrantClient("http://qdrant", httpx.MockTransport(handler))
    with pytest.raises(RagError, match="qdrant_collection_missing"):
        asyncio.run(client.ensure_collection("test", 3, OWNER, create=False))
    with pytest.raises(RagError, match="qdrant_collection_unverified"):
        asyncio.run(client.upsert("test", []))
    with pytest.raises(RagError, match="qdrant_collection_unverified"):
        asyncio.run(client.delete_points("test", []))


def test_delete_never_touches_foreign_collection():
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json={"version": "1.19.2"} if request.url.path == "/"
                              else collection(metadata={"owner": "foreign"}))
    with pytest.raises(RagError, match="qdrant_collection_ownership_mismatch"):
        asyncio.run(QdrantClient("http://qdrant", httpx.MockTransport(handler)).delete_collection("test", OWNER))
    assert calls == ["GET", "GET"]


@pytest.mark.parametrize("version", ["1.18.0", "2.19.2", "1.20.0", None])
def test_reject_incompatible_versions(version):
    client = QdrantClient("http://qdrant", httpx.MockTransport(lambda request: httpx.Response(200, json={"version": version})))
    with pytest.raises(RagError, match="qdrant_version_unsupported"):
        asyncio.run(client.ensure_collection("test", 3, OWNER))


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_remote_errors_are_safe_and_not_retried(status):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(status, headers={"Location": "https://elsewhere"}, text="private-secret")
    with pytest.raises(RagError) as error:
        asyncio.run(QdrantClient("http://qdrant", httpx.MockTransport(handler)).ensure_collection("test", 3, OWNER))
    assert error.value.status_code == 503 and "private-secret" not in str(error.value)
    assert count == 1


def test_untrusted_collection_path_is_rejected_before_request():
    client = QdrantClient("http://qdrant", httpx.MockTransport(lambda request: pytest.fail("network")))
    with pytest.raises(RagError, match="qdrant_collection_invalid"):
        asyncio.run(client.ensure_collection("../foreign", 3, OWNER))


def test_invalid_and_oversized_response(monkeypatch):
    monkeypatch.setattr("app.vector.qdrant.MAX_RESPONSE_BYTES", 5)
    client = QdrantClient("http://qdrant", httpx.MockTransport(lambda request: httpx.Response(200, text="abcdef")))
    with pytest.raises(RagError, match="qdrant_response_too_large"):
        asyncio.run(client.ensure_collection("test", 3, OWNER))


@pytest.mark.parametrize("payload", [[], None, {"status": {}}, {"status": []}, {"status": 1},
                                    {"status": "ok", "result": None},
                                    {"status": "ok", "result": {"config": []}}])
def test_malformed_status_or_collection_is_safe(payload):
    def handler(request):
        value = {"version": "1.19.2"} if request.url.path == "/" else payload
        return httpx.Response(200, json=value)
    with pytest.raises(RagError) as error:
        asyncio.run(QdrantClient("http://qdrant", httpx.MockTransport(handler)).ensure_collection("test", 3, OWNER))
    assert error.value.status_code == 503


@pytest.mark.parametrize("content", [b'{"version":"1.19.2","version":"1.19.2"}',
                                     b'{"version":NaN}', b'\xff', b'not-json'])
def test_invalid_qdrant_json_is_safe(content):
    client = QdrantClient("http://qdrant", httpx.MockTransport(lambda request: httpx.Response(200, content=content)))
    with pytest.raises(RagError, match="qdrant_response_invalid"):
        asyncio.run(client.ensure_collection("test", 3, OWNER))


def test_inflight_revalidation_does_not_invalidate_successful_queries():
    async def scenario():
        blocked, release = asyncio.Event(), asyncio.Event()
        version_checks = 0
        async def handler(request):
            nonlocal version_checks
            if request.url.path == "/":
                version_checks += 1
                if version_checks > 1:
                    blocked.set()
                    await release.wait()
                return httpx.Response(200, json={"version": "1.19.2"})
            if request.url.path.endswith("/points/query"):
                return httpx.Response(200, json={"status": "ok", "result": {"points": []}})
            return httpx.Response(200, json=collection())
        client = QdrantClient("http://qdrant", httpx.MockTransport(handler))
        await client.ensure_collection("test", 3, OWNER)
        task = asyncio.create_task(client.ensure_collection("test", 3, OWNER))
        await blocked.wait()
        try:
            assert await client.query("test", [1, 0, 0], 5) == []
        finally:
            release.set()
            await task
    asyncio.run(scenario())
