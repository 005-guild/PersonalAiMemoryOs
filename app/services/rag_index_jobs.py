"""Restart-safe per-note embedding batches, publication, and owned-point cleanup."""

import math

from sqlalchemy import select

from app.models.base import utcnow
from app.models.rag import RagIndexGeneration, RagIndexJob, RagNoteIndexState
from app.repositories.rag import collection_metadata, generation_dict, job_dict
from app.vector.errors import RagError


class RagJobRunner:
    def __init__(self, indexer):
        self.indexer = indexer

    async def process(self, generation, resolved, job):
        indexer = self.indexer
        vectors = list(job["vectors"] or [None] * len(job["chunks"]))
        while any(vector is None for vector in vectors):
            if indexer._closing:
                return
            offsets = [index for index, vector in enumerate(vectors) if vector is None][:resolved.profile.batch_size]
            intent = {"indices": offsets, "status": "calling", "created_at": utcnow()}
            intents = [*job["intents"], intent]
            # Commit the call intention before touching the paid endpoint.
            job = await indexer.db(lambda repo: repo.set_job(job["id"], status="embedding", intents=intents))
            try:
                reply = await indexer.embedding_client.embed(resolved, [job["chunks"][i]["text"] for i in offsets])
                if (len(reply.vectors) != len(offsets) or any(
                    len(vector) != generation["dimension"] or any(
                    type(number) not in {int, float} or not math.isfinite(number) for number in vector)
                    or not any(vector) for vector in reply.vectors)):
                    raise RagError(502, "embedding_response_invalid")
                for offset, vector in zip(offsets, reply.vectors):
                    vectors[offset] = vector
                intents[-1] = {**intent, "status": "succeeded", "usage": reply.usage}
                job = await indexer.db(lambda repo: repo.set_job(job["id"], vectors=vectors,
                    intents=intents, status="cached" if all(v is not None for v in vectors) else "pending"))
            except Exception as exc:
                code = exc.code if isinstance(exc, RagError) else "embedding_call_failed"
                intents[-1] = {**intent, "status": "outcome_unknown", "error_code": code}
                await indexer.db(lambda repo: repo.set_job(job["id"], intents=intents))
                await indexer.db(lambda repo: repo.fail_job(job["id"], code))
                return
        if indexer._closing:
            return
        job = await indexer.db(lambda repo: repo.set_job(job["id"], status="uploading"))
        points = [{"id": chunk["id"], "vector": vector,
                   "payload": {"knowledge_id": job["knowledge_id"], "generation_id": generation["id"],
                               "content_hash": job["content_hash"], "ordinal": chunk["ordinal"]}}
                  for chunk, vector in zip(job["chunks"], vectors)]
        # An interrupted/failed upload can be repeated using SQLite vectors only.
        for offset in range(0, len(points), 8):
            if indexer._closing:
                return
            await indexer.qdrant_client.upsert(generation["collection"], points[offset:offset + 8])
        await indexer.db(lambda repo: repo.publish(job["id"]))
        await self.cleanup(generation)

    async def cleanup(self, generation):
        def observed(repository):
            jobs = [job_dict(job) for job in repository.session.scalars(select(RagIndexJob).where(
                RagIndexJob.generation_id == generation["id"])) if job.cleanup_ids]
            return jobs, set(repository.valid_chunks(generation["id"]))
        jobs, published_ids = await self.indexer.db(observed)
        for job in jobs:
            if self.indexer._closing:
                return
            # Metadata-only revisions have identical IDs. Preserve any newer publication.
            obsolete_ids = [identity for identity in job["cleanup_ids"] if identity not in published_ids]
            await self.indexer.qdrant_client.delete_points(generation["collection"], obsolete_ids)
            await self.indexer.db(lambda repo, identity=job["id"]: repo.set_job(identity, cleanup_ids=[]))

    async def remove_excluded(self, generation, knowledge_id):
        def observed(repository):
            state = repository.session.get(RagNoteIndexState, (generation["id"], knowledge_id))
            job = repository.session.get(RagIndexJob, state.published_job_id) if state and state.published_job_id else None
            return [chunk["id"] for chunk in job.chunks] if job else []
        ids = await self.indexer.db(observed)
        await self.indexer.qdrant_client.delete_points(generation["collection"], ids)

    async def cleanup_retired(self):
        generations = await self.indexer.db(lambda repo: [generation_dict(generation)
            for generation in repo.session.scalars(select(RagIndexGeneration).where(
                RagIndexGeneration.status == "retired"))])
        for generation in generations:
            if self.indexer._closing:
                return
            await self.indexer.qdrant_client.delete_collection(generation["collection"], collection_metadata(generation))
            def cleaned(repository):
                record = repository.session.get(RagIndexGeneration, generation["id"])
                record.status, record.updated_at = "removed", utcnow()
                # Keep a current note's only successful cache even when it was excluded
                # from this rebuild. Publication clears replaced caches separately.
            await self.indexer.db(cleaned)
