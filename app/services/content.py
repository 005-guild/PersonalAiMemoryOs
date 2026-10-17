"""Versioned business changes; filesystem effects are queued for synchronization."""

from sqlalchemy.orm import Session

from app.models import Knowledge, Source, SyncOperation, SyncState, utcnow
from app.repositories.content import ContentRepository

SOURCE_FIELDS = ("id", "source_type", "title", "author", "url", "content", "version",
                 "created_at", "updated_at", "deleted_at")
KNOWLEDGE_FIELDS = ("id", "source_id", "title", "body", "summary", "category", "tags",
                    "concepts", "version", "created_at", "updated_at", "deleted_at")


class ContentError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def knowledge_snapshot(note: Knowledge) -> dict:
    snapshot = {field: getattr(note, field) for field in KNOWLEDGE_FIELDS}
    snapshot["tags"] = list(note.tags)
    snapshot["concepts"] = list(note.concepts)
    snapshot["deleted"] = note.deleted_at is not None
    return snapshot


class ContentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ContentRepository(session)

    @staticmethod
    def require_version(record, expected_version: int) -> None:
        if record.version != expected_version:
            raise ContentError(409, "The record changed; reload its current version.")

    def source(self, source_id: str, *, include_deleted: bool = False) -> Source:
        record = self.repository.source(source_id)
        if record is None or (record.deleted_at is not None and not include_deleted):
            raise ContentError(404, "Source not found.")
        return record

    def knowledge(self, knowledge_id: str, *, include_deleted: bool = False) -> Knowledge:
        record = self.repository.knowledge(knowledge_id)
        if record is None or (record.deleted_at is not None and not include_deleted):
            raise ContentError(404, "Knowledge not found.")
        return record

    def validate_source(self, source_id: str | None) -> None:
        if source_id is None:
            return
        source = self.repository.source(source_id)
        if source is None or source.deleted_at is not None:
            raise ContentError(409, "source_id must refer to an existing active Source.")

    def source_dict(self, record: Source) -> dict:
        return {field: getattr(record, field) for field in SOURCE_FIELDS}

    def knowledge_dict(self, record: Knowledge) -> dict:
        data = knowledge_snapshot(record)
        state = self.repository.sync_state(record.id)
        data["sync_status"] = state.status if state is not None else "pending"
        return data

    def create_source(self, values: dict) -> dict:
        source = Source(**values)
        self.session.add(source)
        self.session.flush()
        return self.source_dict(source)

    def update_source(self, source_id: str, expected_version: int, values: dict) -> dict:
        source = self.source(source_id, include_deleted=True)
        self.require_version(source, expected_version)
        if source.deleted_at is not None:
            raise ContentError(409, "Restore the Source before editing it.")
        for field, value in values.items():
            setattr(source, field, value)
        source.updated_at = utcnow()
        self.session.flush()
        return self.source_dict(source)

    def delete_source(self, source_id: str, expected_version: int) -> dict:
        source = self.source(source_id, include_deleted=True)
        self.require_version(source, expected_version)
        if self.repository.has_active_knowledge(source_id):
            raise ContentError(409, "Source has active Knowledge; detach or delete it first.")
        if source.deleted_at is None:
            source.deleted_at = utcnow()
        self.session.flush()
        return self.source_dict(source)

    def restore_source(self, source_id: str, expected_version: int) -> dict:
        source = self.source(source_id, include_deleted=True)
        self.require_version(source, expected_version)
        source.deleted_at = None
        self.session.flush()
        return self.source_dict(source)

    def mark_pending(self, note: Knowledge) -> SyncState:
        state = self.repository.sync_state(note.id)
        if state is None:
            state = SyncState(knowledge_id=note.id)
            self.session.add(state)
        state.status = "pending"
        state.last_error = None
        state.missing_since = None
        state.missing_count = 0
        return state

    def create_knowledge(self, values: dict) -> dict:
        self.validate_source(values.get("source_id"))
        note = Knowledge(**values)
        self.session.add(note)
        self.session.flush()
        self.mark_pending(note)
        self.session.flush()
        return self.knowledge_dict(note)

    def update_knowledge(self, knowledge_id: str, expected_version: int, values: dict) -> dict:
        note = self.knowledge(knowledge_id, include_deleted=True)
        self.require_version(note, expected_version)
        if note.deleted_at is not None and set(values) != {"source_id"}:
            raise ContentError(409, "A deleted note may only change source_id; restore it to edit.")
        if "source_id" in values:
            self.validate_source(values["source_id"])
        for field, value in values.items():
            setattr(note, field, value)
        note.updated_at = utcnow()
        self.session.flush()
        self.mark_pending(note)
        self.session.flush()
        return self.knowledge_dict(note)

    def delete_knowledge(self, knowledge_id: str, expected_version: int) -> dict:
        note = self.knowledge(knowledge_id, include_deleted=True)
        self.require_version(note, expected_version)
        if note.deleted_at is None:
            note.deleted_at = utcnow()
            self.session.flush()
            state = self.mark_pending(note)
            self.session.add(SyncOperation(
                knowledge_id=note.id, kind="delete", path=state.path or f"{note.id}.md",
                expected_hash=state.file_hash, expected_version=note.version,
                target_snapshot=knowledge_snapshot(note),
            ))
        self.session.flush()
        return self.knowledge_dict(note)

    def restore_knowledge(self, knowledge_id: str, expected_version: int, values: dict) -> dict:
        note = self.knowledge(knowledge_id, include_deleted=True)
        self.require_version(note, expected_version)
        source_id = values.get("source_id", note.source_id)
        self.validate_source(source_id)
        note.source_id = source_id
        note.deleted_at = None
        note.updated_at = utcnow()
        self.session.flush()
        self.mark_pending(note)
        self.session.flush()
        return self.knowledge_dict(note)

    def list_sources(self, *, include_deleted: bool, offset: int, limit: int) -> dict:
        records, total = self.repository.page(
            Source, include_deleted=include_deleted, offset=offset, limit=limit
        )
        return {"items": [self.source_dict(record) for record in records],
                "total": total, "offset": offset, "limit": limit}

    def list_knowledge(self, *, include_deleted: bool, offset: int, limit: int,
                       source_id: str | None = None) -> dict:
        records, total = self.repository.page(
            Knowledge, include_deleted=include_deleted, offset=offset, limit=limit,
            source_id=source_id,
        )
        return {"items": [self.knowledge_dict(record) for record in records],
                "total": total, "offset": offset, "limit": limit}
