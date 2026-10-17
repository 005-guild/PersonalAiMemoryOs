"""Canonical note values and durable conflict snapshots."""

from sqlalchemy import select

from app.models import Source, SyncConflict, SyncState, utcnow
from app.services.markdown import (
    NoteDocument, content_hash, document_projection, parse_document,
)

EDITABLE = ("title", "body", "summary", "category", "tags", "concepts")


def document(note) -> NoteDocument:
    return NoteDocument(id=note.id, source_id=note.source_id,
                        **{key: getattr(note, key) for key in EDITABLE})


def snapshot(note) -> dict:
    value = document_projection(document(note))
    value["deleted"] = note.deleted_at is not None
    return value


def file_snapshot(doc: NoteDocument) -> dict:
    return {**document_projection(doc), "deleted": False}


def normalize_snapshot(value: dict) -> dict:
    doc = NoteDocument(source_id=value.get("source_id"),
                       **{key: value[key] for key in EDITABLE if key in value})
    return {**document_projection(doc),
            "deleted": bool(value.get("deleted", value.get("deleted_at")))}


def source_available(session, source_id) -> bool:
    if source_id is None:
        return True
    source = session.get(Source, source_id)
    return source is not None and source.deleted_at is None


def state_for(session, note) -> SyncState:
    state = session.get(SyncState, note.id)
    if state is None:
        state = SyncState(knowledge_id=note.id, status="pending")
        session.add(state)
        session.flush()
    return state


def apply_file(note, doc: NoteDocument) -> None:
    # Identity and Source association are deliberately not imported here.
    for key in EDITABLE:
        setattr(note, key, getattr(doc, key))


def baseline(state, value: dict, file_hash, path) -> None:
    state.base = value
    state.base_hash = content_hash(value)
    state.file_hash = file_hash
    state.path = path
    state.missing_since = None
    state.missing_count = 0
    state.last_error = None
    state.last_synced_at = utcnow()
    state.status = "deleted" if value["deleted"] else "synced"


def open_conflict(session, knowledge_id):
    return session.scalars(select(SyncConflict).where(
        SyncConflict.knowledge_id == knowledge_id,
        SyncConflict.status == "open",
    )).first()


def record_conflict(session, note, state, file, reason: str):
    parsed = None
    if file is not None:
        try:
            parsed = file_snapshot(parse_document(file.content))
        except ValueError:
            pass
    previous = open_conflict(session, note.id)
    if previous is not None:
        if (previous.db_version == note.version
                and previous.file_hash == (file.hash if file else None)
                and previous.file_path == (file.path if file else state.path)):
            state.status = "conflict"
            session.commit()
            return previous
        previous.status = "superseded"
        previous.resolved_at = utcnow()
    conflict = SyncConflict(
        knowledge_id=note.id, base=state.base, db_snapshot=snapshot(note),
        file_snapshot=parsed, file_content=file.content if file else None,
        file_path=file.path if file else state.path,
        file_hash=file.hash if file else None, db_version=note.version,
        reason=reason, status="open",
    )
    session.add(conflict)
    state.status = "conflict"
    state.last_error = reason
    session.commit()
    return conflict
