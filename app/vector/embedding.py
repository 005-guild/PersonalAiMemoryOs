"""Bounded, single-attempt OpenAI-compatible embedding transport."""

import asyncio
from dataclasses import dataclass
import json
import math
from typing import Any

import httpx

from app.vector.configuration import ResolvedEmbeddingProfile
from app.vector.errors import RagError

MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field.")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number.")


def _finite_number(value: Any) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


@dataclass(frozen=True)
class EmbeddingReply:
    vectors: list[list[float]]
    usage: dict


def _parse(payload: Any, count: int, dimension: int) -> EmbeddingReply:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RagError(502, "embedding_response_invalid")
    rows = payload["data"]
    if len(rows) != count:
        raise RagError(502, "embedding_response_invalid")
    ordered: list[list[float] | None] = [None] * count
    for row in rows:
        if not isinstance(row, dict):
            raise RagError(502, "embedding_response_invalid")
        index, vector = row.get("index"), row.get("embedding")
        if (type(index) is not int or index < 0 or index >= count or ordered[index] is not None
                or not isinstance(vector, list) or len(vector) != dimension):
            raise RagError(502, "embedding_response_invalid")
        if any(not _finite_number(value) for value in vector):
            raise RagError(502, "embedding_response_invalid")
        if not any(value != 0 for value in vector):
            raise RagError(502, "embedding_response_invalid")
        ordered[index] = [float(value) for value in vector]
    usage = {}
    if isinstance(payload.get("usage"), dict):
        usage = {key: value for key, value in payload["usage"].items()
                 if key in {"prompt_tokens", "total_tokens"} and type(value) is int and value >= 0}
    return EmbeddingReply(ordered, usage)


class EmbeddingClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def aclose(self) -> None:
        """Each operation owns its client and response stream."""

    async def embed(self, resolved: ResolvedEmbeddingProfile, texts: list[str]) -> EmbeddingReply:
        profile = resolved.profile
        if (not isinstance(texts, list) or not texts or len(texts) > profile.batch_size
                or any(not isinstance(text, str) or not text.strip() for text in texts)):
            raise RagError(422, "embedding_batch_invalid")
        headers = {"Content-Type": "application/json"}
        if profile.auth != "none":
            if resolved.api_key is None:
                raise RagError(503, "embedding_api_key_missing")
            key = resolved.api_key.get_secret_value()
            if profile.auth == "x_api_key":
                headers["x-api-key"] = key
            elif profile.auth == "x_goog_api_key":
                headers["x-goog-api-key"] = key
            else:
                headers["Authorization"] = f"Bearer {key}"
        body = {**profile.extra_body, "model": profile.model, "input": texts, "encoding_format": "float"}
        if profile.request_dimensions is not None:
            body["dimensions"] = profile.request_dimensions
        timeout = profile.timeout_seconds
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(transport=self.transport, follow_redirects=False,
                                            timeout=httpx.Timeout(timeout)) as client:
                    async with client.stream("POST", profile.base_url + "/embeddings",
                                             headers=headers, json=body) as response:
                        if not 200 <= response.status_code < 300:
                            raise RagError(502, "embedding_upstream_error")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise RagError(502, "embedding_response_too_large")
                            raw.extend(chunk)
                        try:
                            payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                                                 parse_constant=_constant)
                        except (UnicodeError, ValueError, RecursionError):
                            raise RagError(502, "embedding_response_invalid") from None
                        return _parse(payload, len(texts), profile.dimension)
        except (TimeoutError, httpx.TimeoutException):
            raise RagError(504, "embedding_timeout") from None
        except (httpx.HTTPError, ValueError, OverflowError):
            raise RagError(502, "embedding_upstream_error") from None
