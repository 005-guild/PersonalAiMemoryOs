"""Small Qdrant REST client with bounded requests and collection ownership checks."""

import asyncio
import json
import math
import re
from urllib.parse import urlsplit

import httpx

from app.vector.errors import RagError

_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,180}$")
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


def _finite_number(value) -> bool:
    try:
        return type(value) in {int, float} and math.isfinite(value)
    except (ValueError, OverflowError):
        return False


class QdrantClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        try:
            parsed = urlsplit(base_url)
            parsed.port
        except ValueError:
            raise RagError(503, "qdrant_configuration_invalid") from None
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or "\\" in base_url
                or any(char.isspace() or ord(char) < 32 for char in base_url)):
            raise RagError(503, "qdrant_configuration_invalid")
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self._verified: dict[str, int] = {}

    async def aclose(self) -> None:
        """Each request owns its client; no background connections remain."""

    def _path(self, name: str) -> str:
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise RagError(503, "qdrant_collection_invalid")
        return "/collections/" + name

    async def _request(self, method: str, path: str, body: dict | None = None,
                       allow_missing: bool = False) -> dict | None:
        try:
            async with asyncio.timeout(30):
                async with httpx.AsyncClient(transport=self.transport, follow_redirects=False,
                                            timeout=30) as client:
                    async with client.stream(method, self.base_url + path, json=body) as response:
                        if response.status_code == 404 and allow_missing:
                            return None
                        if not 200 <= response.status_code < 300:
                            raise RagError(503, "qdrant_unavailable")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise RagError(503, "qdrant_response_too_large")
                            raw.extend(chunk)
                        try:
                            payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                                                 parse_constant=_constant)
                        except (ValueError, UnicodeError, RecursionError):
                            raise RagError(503, "qdrant_response_invalid") from None
                        if not isinstance(payload, dict) or payload.get("status") not in (None, "ok"):
                            raise RagError(503, "qdrant_response_invalid")
                        return payload
        except (TimeoutError, httpx.TimeoutException):
            raise RagError(503, "qdrant_timeout") from None
        except (httpx.HTTPError, ValueError, OverflowError):
            raise RagError(503, "qdrant_unavailable") from None

    async def _check_version(self) -> None:
        info = await self._request("GET", "/")
        version = info.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"1\.19\.\d+(?:[-+].*)?", version):
            raise RagError(503, "qdrant_version_unsupported")

    @staticmethod
    def _owned(result: dict, metadata: dict) -> dict:
        config = result.get("config") if isinstance(result, dict) else None
        if not isinstance(config, dict):
            raise RagError(503, "qdrant_response_invalid")
        existing = config.get("metadata")
        if (not isinstance(metadata, dict) or not metadata or not isinstance(existing, dict)
                or any(key not in existing or existing[key] != value for key, value in metadata.items())):
            raise RagError(409, "qdrant_collection_ownership_mismatch")
        return config

    async def ensure_collection(self, name: str, dimension: int, metadata: dict,
                                create: bool = True) -> None:
        # Keep the last successful verification usable while a concurrent check
        # is in flight. Invalidate atomically only when a check actually fails.
        try:
            await self._ensure_collection(name, dimension, metadata, create)
        except BaseException:
            self._verified.pop(name, None)
            raise

    async def _ensure_collection(self, name: str, dimension: int, metadata: dict,
                                 create: bool) -> None:
        path = self._path(name)
        if type(dimension) is not int or dimension <= 0 or not isinstance(metadata, dict) or not metadata:
            raise RagError(503, "qdrant_configuration_invalid")
        await self._check_version()
        info = await self._request("GET", path, allow_missing=True)
        if info is None:
            if not create:
                raise RagError(503, "qdrant_collection_missing")
            await self._request("PUT", path, {"vectors": {"size": dimension, "distance": "Cosine"},
                                               "metadata": metadata})
            info = await self._request("GET", path)
        config = self._owned(info.get("result"), metadata)
        params = config.get("params")
        vectors = params.get("vectors") if isinstance(params, dict) else None
        if (not isinstance(vectors, dict) or type(vectors.get("size")) is not int
                or vectors.get("size") != dimension
                or vectors.get("distance") != "Cosine"):
            raise RagError(409, "qdrant_collection_schema_mismatch")
        self._verified[name] = dimension

    def _verified_path(self, name: str) -> str:
        path = self._path(name)
        if name not in self._verified:
            raise RagError(409, "qdrant_collection_unverified")
        return path

    async def upsert(self, name: str, points: list[dict]) -> None:
        path = self._verified_path(name)
        if not points:
            return
        await self._request("PUT", path + "/points?wait=true", {"points": points})

    async def query(self, name: str, vector: list[float], limit: int) -> list[dict]:
        path = self._verified_path(name)
        info = await self._request("POST", path + "/points/query",
                                   {"query": vector, "limit": limit, "with_payload": True})
        result = info.get("result")
        points = result.get("points") if isinstance(result, dict) else None
        if not isinstance(points, list):
            raise RagError(503, "qdrant_response_invalid")
        valid = []
        for point in points:
            if (not isinstance(point, dict) or type(point.get("id")) not in {int, str}
                    or not _finite_number(point.get("score")) or not isinstance(point.get("payload"), dict)):
                raise RagError(503, "qdrant_response_invalid")
            valid.append({"id": point["id"], "score": point["score"], "payload": point["payload"]})
        return valid

    async def delete_points(self, name: str, ids: list) -> None:
        path = self._verified_path(name)
        if ids:
            await self._request("POST", path + "/points/delete?wait=true", {"points": ids})

    async def delete_collection(self, name: str, metadata: dict) -> None:
        path = self._path(name)
        await self._check_version()
        info = await self._request("GET", path, allow_missing=True)
        if info is not None:
            self._owned(info.get("result"), metadata)
            await self._request("DELETE", path)
        self._verified.pop(name, None)
