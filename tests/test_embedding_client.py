"""Single-attempt, bounded embedding requests and strict vector validation."""

import asyncio
import json

import httpx
from pydantic import SecretStr
import pytest

from app.vector.configuration import EmbeddingProfile, ResolvedEmbeddingProfile
from app.vector.embedding import EmbeddingClient
from app.vector.errors import RagError


def selected(**changes):
    profile = EmbeddingProfile(base_url="https://example.com/v1", model="m", dimension=3, **changes)
    return ResolvedEmbeddingProfile("test", profile, SecretStr("private-secret"), "fingerprint")


def payload(count=1):
    return {"data": [{"index": index, "embedding": [1.0, 0.5, 0.0]} for index in range(count)],
            "usage": {"prompt_tokens": 4, "total_tokens": 4, "untrusted": "secret"}}


@pytest.mark.parametrize("auth,header", [("bearer", "Authorization"), ("auto", "Authorization"),
                                         ("x_api_key", "x-api-key"), ("x_goog_api_key", "x-goog-api-key"),
                                         ("none", None)])
def test_request_auth_and_ordered_vectors(auth, header):
    def handler(request):
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        assert body == {"input": ["中文一", "中文二"], "model": "m", "encoding_format": "float",
                        "dimensions": 3, "task": "retrieval"}
        if header:
            assert request.headers[header] == ("Bearer private-secret" if header == "Authorization" else "private-secret")
        else:
            assert "Authorization" not in request.headers
        reply = payload(2)
        reply["data"].reverse()
        reply["data"][0]["embedding"] = [0, 1, 0]
        return httpx.Response(200, json=reply)
    reply = asyncio.run(EmbeddingClient(httpx.MockTransport(handler)).embed(
        selected(auth=auth, request_dimensions=3, extra_body={"task": "retrieval"}), ["中文一", "中文二"]))
    assert reply.vectors == [[1.0, 0.5, 0.0], [0.0, 1.0, 0.0]]
    assert reply.usage == {"prompt_tokens": 4, "total_tokens": 4}


@pytest.mark.parametrize("data", [
    [], [{"index": 1, "embedding": [1, 2, 3]}], [{"index": True, "embedding": [1, 2, 3]}],
    [{"index": 0, "embedding": [1, 2]}], [{"index": 0, "embedding": [True, 2, 3]}],
    [{"index": 0, "embedding": ["1", 2, 3]}], [{"index": 0, "embedding": [0, 0, 0]}],
    [{"index": 0, "embedding": [1, 2, 3]}, {"index": 0, "embedding": [1, 2, 3]}],
    [None], "invalid",
])
def test_bad_vectors_fail_without_exposing_body(data):
    client = EmbeddingClient(httpx.MockTransport(lambda request: httpx.Response(200, json={"data": data})))
    with pytest.raises(RagError, match="embedding_response_invalid"):
        asyncio.run(client.embed(selected(), ["test"]))


@pytest.mark.parametrize("content", [b'not-json', b'{"data": [], "data": []}',
                                     b'{"data":[{"index":0,"embedding":[NaN,1,2]}]}', b'\xff'])
def test_invalid_json(content):
    client = EmbeddingClient(httpx.MockTransport(lambda request: httpx.Response(200, content=content)))
    with pytest.raises(RagError, match="embedding_response_invalid"):
        asyncio.run(client.embed(selected(), ["test"]))


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_errors_never_retry_or_redirect(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://elsewhere.example"}, text="private-secret")
    with pytest.raises(RagError) as error:
        asyncio.run(EmbeddingClient(httpx.MockTransport(handler)).embed(selected(), ["test"]))
    assert len(calls) == 1
    assert error.value.status_code == 502
    assert "private-secret" not in str(error.value)


def test_total_timeout_and_response_bound(monkeypatch):
    async def slow(request):
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=payload())
    with pytest.raises(RagError) as error:
        asyncio.run(EmbeddingClient(httpx.MockTransport(slow)).embed(selected(timeout_seconds=0.01), ["test"]))
    assert error.value.status_code == 504
    monkeypatch.setattr("app.vector.embedding.MAX_RESPONSE_BYTES", 5)
    with pytest.raises(RagError, match="embedding_response_too_large"):
        asyncio.run(EmbeddingClient(httpx.MockTransport(lambda request: httpx.Response(200, json=payload())))
                    .embed(selected(), ["test"]))


@pytest.mark.parametrize("texts", [[], [""], ["  "], ["test"] * 9])
def test_bad_batch_performs_no_request(texts):
    def forbidden(request):
        pytest.fail("Network must not be reached")
    with pytest.raises(RagError, match="embedding_batch_invalid"):
        asyncio.run(EmbeddingClient(httpx.MockTransport(forbidden)).embed(selected(), texts))


def test_dimensions_not_sent_implicitly_and_usage_is_sanitized():
    def handler(request):
        assert "dimensions" not in json.loads(request.content)
        value = payload()
        value["usage"] = {"prompt_tokens": True, "total_tokens": -1, "other": "secret"}
        return httpx.Response(200, json=value)
    reply = asyncio.run(EmbeddingClient(httpx.MockTransport(handler)).embed(selected(), ["test"]))
    assert reply.usage == {}
