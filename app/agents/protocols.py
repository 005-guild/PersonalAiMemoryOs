"""Wire-format adapters for four text-generation API families."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.agents.configuration import ResolvedProfile
from app.agents.errors import AIError


@dataclass(frozen=True)
class ModelReply:
    text: str
    usage: dict[str, int | None]


def _merge(target: dict, extension: dict) -> dict:
    for key, value in extension.items():
        if isinstance(target.get(key), dict):
            if not isinstance(value, dict):
                raise AIError(503, "ai_configuration_invalid")
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def build_request(resolved: ResolvedProfile, system: str, user: str) -> tuple[str, dict, dict]:
    profile = resolved.profile
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    mode = profile.auth
    if mode == "auto":
        mode = {"anthropic_messages": "x_api_key", "gemini_generate_content": "x_goog_api_key"}.get(
            profile.protocol, "bearer"
        )
    if resolved.api_key is not None and mode != "none":
        secret = resolved.api_key.get_secret_value()
        if mode == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        else:
            headers[{"x_api_key": "x-api-key", "x_goog_api_key": "x-goog-api-key"}[mode]] = secret

    if profile.protocol == "openai_chat":
        path = "/chat/completions"
        body: dict[str, Any] = {
            "model": profile.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            profile.token_limit_field: profile.max_output_tokens,
            "stream": False,
        }
        if profile.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
    elif profile.protocol == "openai_responses":
        path = "/responses"
        body = {"model": profile.model, "instructions": system, "input": user,
                "max_output_tokens": profile.max_output_tokens, "stream": False, "store": False}
    elif profile.protocol == "anthropic_messages":
        path = "/messages"
        headers["anthropic-version"] = profile.anthropic_version
        body = {"model": profile.model, "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": profile.max_output_tokens, "stream": False}
    else:
        path = f"/models/{quote(profile.model, safe='')}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"maxOutputTokens": profile.max_output_tokens}}
    return profile.base_url + path, headers, _merge(body, profile.extra_body)


def _failure(code: str = "invalid_model_response") -> None:
    raise AIError(502, code)


def _usage(raw: Any, input_key: str, output_key: str, total_key: str) -> dict[str, int | None]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int | None] = {}
    for target, key in (("input_tokens", input_key), ("output_tokens", output_key), ("total_tokens", total_key)):
        value = raw.get(key)
        if type(value) is int and value >= 0:
            result[target] = value
    if "total_tokens" not in result and "input_tokens" in result and "output_tokens" in result:
        result["total_tokens"] = result["input_tokens"] + result["output_tokens"]  # type: ignore[operator]
    return result


def _chat(payload: dict) -> ModelReply:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        _failure()
    choice = choices[0]
    finish = choice.get("finish_reason")
    if finish == "length":
        _failure("model_output_truncated")
    if finish == "content_filter":
        _failure("model_refused")
    if finish != "stop":
        _failure()
    message = choice.get("message")
    if not isinstance(message, dict):
        _failure()
    if message.get("refusal"):
        _failure("model_refused")
    if message.get("tool_calls") or message.get("function_call"):
        _failure()
    content = message.get("content")
    if isinstance(content, list):
        text = []
        for part in content:
            if not isinstance(part, dict):
                _failure()
            if part.get("type") == "refusal":
                _failure("model_refused")
            if part.get("type") != "text" or not isinstance(part.get("text"), str):
                _failure()
            text.append(part["text"])
        content = "".join(text)
    if not isinstance(content, str) or not content.strip():
        _failure()
    return ModelReply(content, _usage(payload.get("usage"), "prompt_tokens", "completion_tokens", "total_tokens"))


def _responses(payload: dict) -> ModelReply:
    if payload.get("status") == "incomplete":
        _failure("model_output_truncated")
    if payload.get("status") != "completed":
        _failure()
    output = payload.get("output")
    if not isinstance(output, list):
        _failure()
    text = []
    for item in output:
        if not isinstance(item, dict):
            _failure()
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or item.get("role") != "assistant":
            _failure()
        if item.get("status", "completed") != "completed" or not isinstance(item.get("content"), list):
            _failure()
        for part in item["content"]:
            if not isinstance(part, dict):
                _failure()
            if part.get("type") == "refusal":
                _failure("model_refused")
            if part.get("type") != "output_text" or not isinstance(part.get("text"), str):
                _failure()
            text.append(part["text"])
    content = "".join(text)
    if not content.strip():
        _failure()
    return ModelReply(content, _usage(payload.get("usage"), "input_tokens", "output_tokens", "total_tokens"))


def _anthropic(payload: dict) -> ModelReply:
    stop = payload.get("stop_reason")
    if stop == "max_tokens":
        _failure("model_output_truncated")
    if stop == "refusal":
        _failure("model_refused")
    if stop not in {"end_turn", "stop_sequence"}:
        _failure()
    if not isinstance(payload.get("content"), list):
        _failure()
    text = []
    for part in payload["content"]:
        if not isinstance(part, dict):
            _failure()
        if part.get("type") in {"thinking", "redacted_thinking"}:
            continue
        if part.get("type") != "text" or not isinstance(part.get("text"), str):
            _failure()
        text.append(part["text"])
    content = "".join(text)
    if not content.strip():
        _failure()
    return ModelReply(content, _usage(payload.get("usage"), "input_tokens", "output_tokens", "total_tokens"))


def _gemini(payload: dict) -> ModelReply:
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        _failure("model_refused")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        _failure()
    candidate = candidates[0]
    finish = candidate.get("finishReason")
    if finish == "MAX_TOKENS":
        _failure("model_output_truncated")
    if finish in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
        _failure("model_refused")
    if finish != "STOP":
        _failure()
    content = candidate.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("parts"), list):
        _failure()
    text = []
    for part in content["parts"]:
        if not isinstance(part, dict):
            _failure()
        if part.get("thought") is True:
            continue
        if not isinstance(part.get("text"), str) or "functionCall" in part:
            _failure()
        text.append(part["text"])
    result = "".join(text)
    if not result.strip():
        _failure()
    return ModelReply(result, _usage(payload.get("usageMetadata"), "promptTokenCount", "candidatesTokenCount", "totalTokenCount"))


def parse_response(protocol: str, payload: Any) -> ModelReply:
    if not isinstance(payload, dict) or payload.get("error"):
        _failure()
    try:
        parser = {"openai_chat": _chat, "openai_responses": _responses,
                  "anthropic_messages": _anthropic, "gemini_generate_content": _gemini}[protocol]
        return parser(payload)
    except (KeyError, TypeError, ValueError, RecursionError):
        # Untrusted wire fields may be arrays/objects where a scalar is expected.
        raise AIError(502, "invalid_model_response") from None
