"""Load only candidate publications and chunks, never vector-cache columns."""

from sqlalchemy import select

from app.models.content import Knowledge
from app.models.rag import RagIndexJob, RagNoteIndexState
from app.repositories.rag import hash_note


def publications(repository, generation_id, identities):
    if not identities:
        return {}
    state, job = RagNoteIndexState, RagIndexJob
    rows = repository.session.execute(select(
        state.knowledge_id, state.version, state.content_hash, job.chunks
    ).join(job, job.id == state.published_job_id).where(
        state.generation_id == generation_id, state.knowledge_id.in_(identities),
        state.status == "published", job.status == "published",
        job.generation_id == generation_id, job.knowledge_id == state.knowledge_id,
        job.version == state.version, job.content_hash == state.content_hash))
    result = {}
    for identity, version, digest, chunks in rows:
        note, reason = repository.note(identity)
        if reason or note["version"] != version or hash_note(note) != digest:
            continue
        result[identity] = {"note": note, "chunks": chunks, "content_hash": digest,
                            "generation_id": generation_id}
    return result


def title_candidates(repository, generation_id, query):
    # Literal contains, including %, _ and backslash; deterministic tie order.
    identities = repository.session.scalars(select(Knowledge.id).join(
        RagNoteIndexState, RagNoteIndexState.knowledge_id == Knowledge.id
    ).where(RagNoteIndexState.generation_id == generation_id,
            RagNoteIndexState.status == "published", Knowledge.deleted_at.is_(None),
            Knowledge.title.contains(query, autoescape=True))
        .order_by(Knowledge.updated_at.desc(), Knowledge.id).limit(10)).all()
    return publications(repository, generation_id, identities)
