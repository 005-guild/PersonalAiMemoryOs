"""Candidate-only retrieval, optional local reranking and note-level evidence."""

import asyncio
from threading import BoundedSemaphore

from app.repositories.rag import collection_metadata, generation_dict
from app.repositories.rag_candidates import publications, title_candidates
from app.services.rag_index_views import status
from app.services.rag_reading import build_reading
from app.vector.errors import RagError


class RagRetrievalService:
    def __init__(self, indexer, embedding_client, qdrant_client, reranker, *, query_gate=None):
        self.indexer, self.embedding, self.qdrant, self.reranker = indexer, embedding_client, qdrant_client, reranker
        self._gate = query_gate if query_gate is not None else BoundedSemaphore(1)

    def snapshot(self, operation=None):
        resolved = self.indexer.registry.resolve()
        fingerprint, _ = self.indexer.configuration(resolved)
        def read(repo):
            generation = generation_dict(repo.current())
            if generation is None:
                raise RagError(503, "rag_index_missing")
            if generation["fingerprint"] != fingerprint:
                raise RagError(409, "rag_rebuild_required")
            if generation["status"] != "ready" or generation["error_code"]:
                raise RagError(503, "rag_index_unavailable")
            return generation, resolved, status(self.indexer, repo), operation(repo, generation) if operation else None
        return self.indexer.transaction(read)

    async def retrieve(self, query, max_notes=5, *, knowledge_ids=None):
        if not query.strip() or len(query) > 2000 or type(max_notes) is not int or not 1 <= max_notes <= 10:
            raise RagError(422, "rag_query_invalid")
        if not self._gate.acquire(blocking=False):
            raise RagError(429, "embedding_query_busy")
        try:
            generation, resolved, summary, _ = await asyncio.to_thread(self.snapshot)
            await self.qdrant.ensure_collection(generation["collection"], generation["dimension"],
                                               collection_metadata(generation), create=False)
            if not summary["counts"]["published"]:
                if summary["counts"]["pending"] or summary["counts"]["failed"]:
                    raise RagError(503, "rag_index_not_ready")
                return {"notes": [], "contexts": [], "index_incomplete": summary["index_incomplete"],
                        "rerank": {"enabled": self.reranker.options.enabled}}
            reply = await self.embedding.embed(resolved, [query])
            points = await self.qdrant.query(generation["collection"], reply.vectors[0], 50,
                                              **({'knowledge_ids':knowledge_ids} if knowledge_ids is not None else {}))
            def load(repo, current):
                selected = publications(repo, current["id"], {p["payload"].get("knowledge_id") for p in points})
                titles = title_candidates(repo, current["id"], query)
                if knowledge_ids is not None:
                    selected = {k:v for k,v in selected.items() if k in knowledge_ids}
                    titles = {k:v for k,v in titles.items() if k in knowledge_ids}
                return selected, titles
            current, _, summary, (selected, titles) = await asyncio.to_thread(self.snapshot, load)
            if current["id"] != generation["id"]:
                raise RagError(409, "context_changed")
            candidates = {}
            for point in points:
                payload = point["payload"]
                publication = selected.get(payload.get("knowledge_id"))
                if (not publication or payload.get("generation_id") != current["id"]
                        or payload.get("content_hash") != publication["content_hash"]):
                    continue
                chunk = next((ch for ch in publication["chunks"] if ch["id"] == str(point["id"])), None)
                if chunk:
                    candidates[chunk["id"]] = (publication, chunk, point["score"])
            for publication in titles.values():
                ordered = sorted(publication["chunks"], key=lambda ch: (query not in ch["text"], ch["ordinal"]))
                for chunk in ordered[:3]:
                    candidates.setdefault(chunk["id"], (publication, chunk, None))
            entries = list(candidates.values())
            if self.reranker.options.enabled:
                scores = await self.reranker.rank(query, [p["note"]["title"] + "\n" + ch["text"] for p,ch,_ in entries])
            else:
                scores = [score if score is not None else 0.0 for _,_,score in entries]
            groups = {}
            ranked = sorted(zip(entries, scores), key=lambda item: (-item[1], item[0][1]["id"]))
            for (publication, chunk, dense_score), score in ranked:
                identity = publication["note"]["id"]
                group = groups.setdefault(identity, {**publication, "matches": [], "score": score})
                group["matches"].append({"chunk_id": chunk["id"], "text": chunk["text"],
                    "start": chunk["start"], "end": chunk["end"], "score": score, "vector_score": dense_score})
            notes, contexts = build_reading(list(groups.values())[:max_notes])
            if not await asyncio.to_thread(self.validate_context, contexts):
                raise RagError(409, "context_changed")
            return {"notes": notes, "contexts": contexts, "index_incomplete": summary["index_incomplete"],
                    "rerank": {"enabled": self.reranker.options.enabled,
                               "model": self.reranker.options.model, "revision": self.reranker.options.revision}}
        finally:
            self._gate.release()

    def validate_context(self, contexts):
        try:
            generation, _, _, records = self.snapshot(lambda repo, g: publications(
                repo, g["id"], {c["knowledge_id"] for c in contexts}))
            for item in contexts:
                pub = records.get(item["knowledge_id"])
                if (not pub or item["generation_id"] != generation["id"]
                        or item["version"] != pub["note"]["version"] or item["content_hash"] != pub["content_hash"]):
                    return False
                for field in ("path", "source_id", "source", "source_ids", "sources"):
                    item[field] = pub["note"][field]
            return True
        except RagError:
            return False

    async def search(self, query, top_k=5):
        # Adapt to the existing, strictly validated answer renderer.
        result = await self.retrieve(query, top_k)
        return {**result, "items": result["contexts"]}
