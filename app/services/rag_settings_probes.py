"""Explicit one-attempt diagnostics; never touch index storage or collections."""

from threading import Lock

from pydantic import SecretStr
from starlette.concurrency import run_in_threadpool

from app.services.ai_settings import _hash
from app.services.configuration_files import CONFIGURATION_LOCK
from app.services.rag_settings_state import RAGSettingsError
from app.vector.configuration import EmbeddingProfile, ResolvedEmbeddingProfile
from app.vector.embedding import EmbeddingClient
from app.vector.errors import RagError
from app.vector.qdrant import QdrantClient


class RAGSettingsProbes:
    def __init__(self, service, *, embedding_client=None, qdrant_transport=None):
        self.service = service
        self.embedding_client = embedding_client
        self.qdrant_transport = qdrant_transport
        self._busy = Lock()

    def snapshot(self, revision):
        with CONFIGURATION_LOCK:
            snapshot = self.service.snapshot()
            if snapshot["revision"] != revision:
                raise RAGSettingsError(409, "configuration_changed")
            return snapshot

    async def run(self, payload):
        if payload.target == "embedding" and not payload.confirm_embedding:
            raise RAGSettingsError(422, "embedding_test_confirmation_required")
        if not self._busy.acquire(blocking=False):
            raise RAGSettingsError(429, "configuration_test_busy")
        try:
            snapshot = await run_in_threadpool(self.snapshot, payload.expected_revision)
            if payload.target == "qdrant":
                client = QdrantClient(snapshot["qdrant_url"], transport=self.qdrant_transport)
                try:
                    await client._check_version()
                finally:
                    await client.aclose()
                result = {"target": "qdrant", "status": "ok", "read_only": True}
            else:
                identifier = payload.profile_id or snapshot["default"]
                profile = snapshot["profiles"].get(identifier)
                if profile is None:
                    raise RAGSettingsError(422, "embedding_profile_unknown")
                profile = EmbeddingProfile.model_validate(profile)
                if not profile.enabled:
                    raise RAGSettingsError(409, "embedding_profile_disabled")
                value = snapshot["keys"].get((profile.api_key_ref or "").casefold(), "")
                if profile.auth != "none" and not value.strip():
                    raise RAGSettingsError(503, "embedding_api_key_missing")
                resolved = ResolvedEmbeddingProfile(identifier, profile, SecretStr(value) if value else None, _hash(profile.model_dump()))
                client = self.embedding_client if self.embedding_client is not None else EmbeddingClient()
                try:
                    reply = await client.embed(resolved, ["知识库向量连接测试。"])
                finally:
                    if self.embedding_client is None:
                        await client.aclose()
                result = {"target": "embedding", "status": "ok", "profile_id": identifier,
                          "dimension": len(reply.vectors[0]), "usage": reply.usage, "calls": 1}
            await run_in_threadpool(self.snapshot, payload.expected_revision)
            return result
        except RagError as error:
            raise RAGSettingsError(error.status_code, error.code) from None
        except RAGSettingsError:
            raise
        except Exception:
            raise RAGSettingsError(503, "configuration_test_failed") from None
        finally:
            self._busy.release()
