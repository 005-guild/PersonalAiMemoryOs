"""Single-attempt, bounded TEI relevance scoring; no generation or embeddings."""

import asyncio
import json
from threading import BoundedSemaphore

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.vector.embedding import _constant, _finite_number, _unique
from app.vector.errors import RagError

_REQUEST_GATE = BoundedSemaphore(1)


class RerankOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    enabled: bool = False
    url: str = Field(default="http://127.0.0.1:18081", max_length=2048)
    model: str = Field(default="BAAI/bge-reranker-v2-m3", min_length=1, max_length=200)
    revision: str = Field(default="", max_length=200)
    timeout_seconds: float = Field(default=60.0, ge=1, le=180)

    @field_validator("url")
    @classmethod
    def valid_url(cls, value):
        from app.config import Settings
        return Settings.validate_qdrant_url(value)

    @field_validator("model", "revision")
    @classmethod
    def safe_text(cls, value):
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Invalid reranker identity.")
        return value


ENV_FIELDS = {key: "MEMORY_OS_RAG_RERANK_" + suffix for key, suffix in (
    ("enabled", "ENABLED"), ("url", "URL"), ("model", "MODEL"),
    ("revision", "REVISION"), ("timeout_seconds", "TIMEOUT_SECONDS"))}


def options_from_settings(settings):
    return RerankOptions(**{key: getattr(settings, "rag_rerank_" + key) for key in ENV_FIELDS})


def options_from_environment(values):
    # Environment strings require coercion; HTTP writes remain strict.
    return RerankOptions.model_validate({key: values[name] for key, name in ENV_FIELDS.items() if name in values}, strict=False)


class RerankClient:
    def __init__(self, options, *, transport=None):
        self.options, self.transport = options, transport
        self._gate = _REQUEST_GATE

    async def aclose(self):
        pass

    async def rank(self, query, texts):
        if not texts:
            return []
        if len(texts) > 80 or any(not text.strip() for text in texts):
            raise RagError(422, "rerank_input_invalid")
        if not self._gate.acquire(blocking=False):
            raise RagError(429, "rerank_busy")
        try:
            async with asyncio.timeout(self.options.timeout_seconds):
                async with httpx.AsyncClient(transport=self.transport, timeout=self.options.timeout_seconds,
                                            follow_redirects=False, trust_env=False) as client:
                    async with client.stream("POST", self.options.url + "/rerank", json={
                        "query": query, "texts": texts, "truncate": False, "raw_scores": True,
                        "return_text": False,
                    }) as response:
                        if not 200 <= response.status_code < 300:
                            raise RagError(502, "rerank_upstream_error")
                        raw = bytearray()
                        async for block in response.aiter_bytes():
                            raw.extend(block)
                            if len(raw) > 1024 * 1024:
                                raise RagError(502, "rerank_response_too_large")
                        try:
                            rows = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
                            if not isinstance(rows, list) or len(rows) != len(texts):
                                raise ValueError()
                            scores = [None] * len(texts)
                            for row in rows:
                                index, score = row["index"], row["score"]
                                if (type(index) is not int or not 0 <= index < len(texts)
                                        or scores[index] is not None or not _finite_number(score)):
                                    raise ValueError()
                                scores[index] = float(score)
                            return scores
                        except (ValueError, TypeError, KeyError, RecursionError):
                            raise RagError(502, "rerank_response_invalid") from None
        except (TimeoutError, httpx.TimeoutException):
            raise RagError(504, "rerank_timeout") from None
        except httpx.HTTPError:
            raise RagError(503, "rerank_unavailable") from None
        finally:
            self._gate.release()
