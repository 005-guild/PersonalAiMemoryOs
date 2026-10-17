"""Real HTTPX request/response handling against four deterministic mock protocols."""

import asyncio
import hashlib
import json

import httpx
from pydantic import SecretStr
import pytest

from app.agents.configuration import AIProfile, ResolvedProfile
from app.agents.errors import AIError
from app.agents.protocols import build_request
from app.agents.transport import MAX_RESPONSE_BYTES, ModelClient


def resolved(protocol="openai_chat", **changes) -> ResolvedProfile:
    profile = AIProfile(protocol=protocol, base_url="https://example.com/v1", model="mock-model", **changes)
    return ResolvedProfile("mock", profile, SecretStr("mock-secret"), hashlib.sha256(b"mock").hexdigest())


def response_payload(protocol: str, text: str = '{"title":"中文"}') -> dict:
    if protocol == "openai_chat":
        return {"choices": [{"finish_reason": "stop", "message": {"content": text,
                "reasoning_content": "never exposed"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}
    if protocol == "openai_responses":
        return {"status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}}
    if protocol == "anthropic_messages":
        return {"stop_reason": "end_turn", "content": [
            {"type": "thinking", "thinking": "never exposed"}, {"type": "text", "text": text}],
            "usage": {"input_tokens": 10, "output_tokens": 20}}
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"thought": True, "text": "never exposed"}, {"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20, "totalTokenCount": 30}}


@pytest.mark.parametrize("protocol,path,header", [
    ("openai_chat", "/v1/chat/completions", "authorization"),
    ("openai_responses", "/v1/responses", "authorization"),
    ("anthropic_messages", "/v1/messages", "x-api-key"),
    ("gemini_generate_content", "/v1/models/mock-model:generateContent", "x-goog-api-key"),
])
def test_four_protocol_requests_and_text_usage(protocol: str, path: str, header: str):
    def handler(request: httpx.Request):
        assert request.url.path == path
        assert request.method == "POST"
        assert request.headers[header] == ("Bearer mock-secret" if header == "authorization" else "mock-secret")
        body = json.loads(request.content)
        assert "system instructions" in json.dumps(body)
        assert "source text" in json.dumps(body)
        assert "temperature" not in body
        if protocol == "openai_chat":
            assert body["max_tokens"] == 4096
            assert body["stream"] is False
            assert "response_format" not in body
        elif protocol == "openai_responses":
            assert body["max_output_tokens"] == 4096
            assert body["store"] is False
        elif protocol == "anthropic_messages":
            assert body["max_tokens"] == 4096
            assert request.headers["anthropic-version"] == "2023-06-01"
        else:
            assert body["generationConfig"]["maxOutputTokens"] == 4096
            assert "stream" not in body
        return httpx.Response(200, json=response_payload(protocol))

    reply = asyncio.run(ModelClient(httpx.MockTransport(handler)).generate(resolved(protocol), "system instructions", "source text"))
    assert reply.text == '{"title":"中文"}'
    assert reply.usage == {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}


def test_deepseek_json_thinking_and_chat_token_field():
    profile = resolved(response_format="json_object", token_limit_field="max_completion_tokens",
                       extra_body={"thinking": {"type": "disabled"}})
    _, _, body = build_request(profile, "s", "u")
    assert body["max_completion_tokens"] == 4096
    assert "max_tokens" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}


def test_gemini_safe_deep_extension_preserves_output_limit():
    profile = resolved("gemini_generate_content", extra_body={"generationConfig": {"temperature": 0.3}})
    _, _, body = build_request(profile, "s", "u")
    assert body["generationConfig"] == {"maxOutputTokens": 4096, "temperature": 0.3}


@pytest.mark.parametrize("replacement", [None, [], "disabled"])
def test_merge_defense_keeps_output_limit_if_profile_mutated(replacement):
    profile = resolved("gemini_generate_content")
    profile.profile.extra_body["generationConfig"] = replacement
    with pytest.raises(AIError) as caught:
        build_request(profile, "s", "u")
    assert (caught.value.status_code, caught.value.code) == (503, "ai_configuration_invalid")


@pytest.mark.parametrize("auth,header", [("bearer", "Authorization"), ("x_api_key", "x-api-key"),
                                        ("x_goog_api_key", "x-goog-api-key"), ("none", None)])
def test_explicit_auth_override(auth: str, header: str | None):
    _, headers, _ = build_request(resolved(auth=auth), "s", "u")
    if header is None:
        assert not any(key.lower() in {"authorization", "x-api-key", "x-goog-api-key"} for key in headers)
    else:
        assert headers[header] == ("Bearer mock-secret" if auth == "bearer" else "mock-secret")


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500, 503])
def test_upstream_http_errors_safe_and_never_retried(status: int):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://other.example"}, text="PRIVATE-UPSTREAM-BODY")
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(handler)).generate(resolved(), "private prompt", "private source"))
    assert caught.value.status_code == 502
    assert caught.value.code == "ai_upstream_error"
    assert "PRIVATE" not in str(caught.value)
    assert len(requests) == 1


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b'{"choices":NaN}', b'{"choices":[],"choices":[]}', b"[]"])
def test_invalid_wire_response_rejected(raw: bytes):
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, content=raw))).generate(resolved(), "s", "u"))
    assert caught.value.code == "invalid_model_response"


@pytest.mark.parametrize("protocol,change,expected", [
    ("openai_chat", "truncated", "model_output_truncated"),
    ("openai_chat", "refused", "model_refused"),
    ("openai_responses", "truncated", "model_output_truncated"),
    ("openai_responses", "refused", "model_refused"),
    ("anthropic_messages", "truncated", "model_output_truncated"),
    ("anthropic_messages", "refused", "model_refused"),
    ("gemini_generate_content", "truncated", "model_output_truncated"),
    ("gemini_generate_content", "refused", "model_refused"),
])
def test_refusal_and_truncation_are_not_valid_results(protocol: str, change: str, expected: str):
    payload = response_payload(protocol)
    if protocol == "openai_chat":
        if change == "truncated":
            payload["choices"][0]["finish_reason"] = "length"
        else:
            payload["choices"][0]["message"]["refusal"] = "private refusal"
    elif protocol == "openai_responses":
        if change == "truncated":
            payload["status"] = "incomplete"
        else:
            payload["output"][1]["content"] = [{"type": "refusal", "refusal": "private refusal"}]
    elif protocol == "anthropic_messages":
        payload["stop_reason"] = "max_tokens" if change == "truncated" else "refusal"
    else:
        payload["candidates"][0]["finishReason"] = "MAX_TOKENS" if change == "truncated" else "SAFETY"
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, json=payload))).generate(resolved(protocol), "s", "u"))
    assert caught.value.code == expected


@pytest.mark.parametrize("protocol", ["openai_chat", "openai_responses", "anthropic_messages", "gemini_generate_content"])
def test_empty_final_text_rejected_even_with_reasoning(protocol: str):
    payload = response_payload(protocol, "  ")
    with pytest.raises(AIError):
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, json=payload))).generate(resolved(protocol), "s", "u"))


def test_response_limit_applies_during_streaming():
    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b" " * MAX_RESPONSE_BYTES
            yield b"x"
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, stream=Oversized()))).generate(resolved(), "s", "u"))
    assert caught.value.code == "ai_response_too_large"


def test_total_timeout_limits_drip_stream():
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield b" "
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowStream()))).generate(resolved(timeout_seconds=0.03), "s", "u"))
    assert (caught.value.status_code, caught.value.code) == (504, "ai_timeout")


def test_transport_error_does_not_include_request_or_credentials():
    def handler(request):
        raise httpx.ConnectError("PRIVATE-SECRET https://private.example", request=request)
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(handler)).generate(resolved(), "s", "u"))
    assert str(caught.value) == "ai_upstream_error"


@pytest.mark.parametrize("protocol,payload", [
    ("anthropic_messages", {"stop_reason": [], "content": []}),
    ("anthropic_messages", {"stop_reason": "end_turn", "content": [{"type": []}]}),
    ("gemini_generate_content", {"candidates": [{"finishReason": {}}]}),
])
def test_malformed_wire_field_types_are_safe_errors(protocol: str, payload: dict):
    with pytest.raises(AIError) as caught:
        asyncio.run(ModelClient(httpx.MockTransport(lambda request: httpx.Response(200, json=payload))).generate(resolved(protocol), "s", "u"))
    assert (caught.value.status_code, caught.value.code) == (502, "invalid_model_response")
