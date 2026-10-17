"""Qdrant chooses candidates; SQLite supplies and validates all returned content."""

import asyncio
from threading import BoundedSemaphore

from app.repositories.rag import collection_metadata
from app.vector.errors import RagError


class RagSearchService:
    def __init__(self, indexer, registry, embedding_client, qdrant_client):
        self.indexer, self.registry = indexer, registry
        self.embedding_client, self.qdrant_client = embedding_client, qdrant_client
        self._gate = BoundedSemaphore(1)

    async def search(self, query: str, top_k: int = 5) -> dict:
        if (not isinstance(query, str) or not query.strip() or len(query) > 2000
                or type(top_k) is not int or not 1 <= top_k <= 10):
            raise RagError(422, "rag_query_invalid")
        if not self._gate.acquire(blocking=False):
            raise RagError(429, "embedding_query_busy")
        try:
            generation, resolved, valid, status = await self.indexer.search_snapshot()
            await self.qdrant_client.ensure_collection(
                generation["collection"], generation["dimension"], collection_metadata(generation), create=False
            )
            if not valid:
                counts = status["counts"]
                if counts["pending"] or counts["failed"]:
                    raise RagError(503, "rag_index_not_ready")
                return {"items": [], "index_incomplete": status["index_incomplete"]}
            reply = await self.embedding_client.embed(resolved, [query])
            points = await self.qdrant_client.query(generation["collection"], reply.vectors[0], min(50, top_k * 5))
            current, _, valid, status = await asyncio.to_thread(self.indexer.checked_snapshot)
            if current["id"] != generation["id"]:
                raise RagError(409, "context_changed")
            items, seen = [], set()
            for point in points:
                identity = str(point["id"])
                item = valid.get(identity)
                if item is None or identity in seen:
                    continue
                payload = point["payload"]
                if (payload.get("knowledge_id") != item["knowledge_id"]
                        or payload.get("content_hash") != item["content_hash"]
                        or payload.get("generation_id") != generation["id"]):
                    continue
                items.append({**item, "score": point["score"]})
                seen.add(identity)
                if len(items) == top_k:
                    break
            return {"items": items, "index_incomplete": status["index_incomplete"]}
        finally:
            self._gate.release()

    def validate_context(self, items: list[dict]) -> bool:
        try:
            generation, _, valid, _ = self.indexer.checked_snapshot()
        except RagError:
            return False
        for item in items:
            current = valid.get(item["chunk_id"])
            if (current is None or item["generation_id"] != generation["id"]
                    or any(current[field] != item[field] for field in
                           ("knowledge_id", "version", "content_hash", "text"))):
                return False
            for field in ("path", "source_id", "source"):
                item[field] = current[field]
        return True
