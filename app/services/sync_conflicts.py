"""Explicit conflict resolution against the exact snapshots the user reviewed."""

from sqlalchemy import select

from app.models import Knowledge, SyncConflict, SyncOperation, utcnow
from app.services.content import ContentError, ContentService
from app.services.files import read_file, scan_files
from app.services.markdown import parse_document
from app.services.sync_state import (
    apply_file, baseline, document, record_conflict, snapshot,
    source_available, state_for,
)


class ConflictResolver:
    def __init__(self, synchronizer):
        self.sync = synchronizer

    def resolve(self, conflict_id, choice):
        with self.sync.lock, self.sync.database.session() as session:
            self.sync._prepare_vault(session)
            conflict = session.get(SyncConflict, conflict_id)
            if conflict is None:
                raise ContentError(404, "Conflict not found.")
            if conflict.status != "open":
                raise ContentError(409, "The conflict is no longer open.")
            note = session.get(Knowledge, conflict.knowledge_id)
            state = state_for(session, note)
            file = self._locate(note, state, conflict)
            if (note.version != conflict.db_version
                    or (file.hash if file else None) != conflict.file_hash
                    or (file.path if file else state.path) != conflict.file_path):
                record_conflict(session, note, state, file, "changed_after_conflict")
                raise ContentError(409, "The note or file changed; review the latest conflict.")
            doc = None
            if file is not None:
                try:
                    doc = parse_document(file.content)
                except ValueError:
                    if choice == "markdown":
                        raise ContentError(409, "Repair invalid Markdown before selecting it.") from None
                if doc is not None and doc.id != note.id:
                    identity_claim = session.scalars(select(SyncOperation).where(
                        SyncOperation.knowledge_id == note.id,
                        SyncOperation.kind == "identity", SyncOperation.path == file.path,
                    )).first()
                    if not (doc.id is None and identity_claim is not None):
                        raise ContentError(409, "The file is occupied by a different identity.")
            if choice == "markdown":
                if doc is None:
                    note.deleted_at = utcnow()
                else:
                    if not source_available(session, note.source_ids):
                        raise ContentError(409, "Restore or detach the deleted Source first.")
                    apply_file(note, doc)
                    note.deleted_at = None
                session.flush()
            elif note.deleted_at is None and not source_available(session, note.source_ids):
                raise ContentError(409, "Restore or detach the deleted Source first.")
            for operation in session.scalars(select(SyncOperation).where(
                SyncOperation.knowledge_id == note.id,
                SyncOperation.status.in_(["pending", "error", "blocked"]),
            )):
                operation.status = "cancelled"
            conflict.status, conflict.resolved_at = "resolved", utcnow()
            path = file.path if file else state.path or f"{note.id}.md"
            if choice == "markdown" and (doc is None or (
                    doc.id == note.id and doc.association_ids == note.source_ids)):
                baseline(state, snapshot(note), file.hash if file else None, path)
                session.commit()
            else:
                operation = self.sync.journal.queue(
                    session, note, state, path, file,
                    None if note.deleted_at else document(note),
                    "delete" if note.deleted_at else "write",
                )
                self.sync.journal.execute(session, operation)
            return ContentService(session).knowledge_dict(note)

    def _locate(self, note, state, conflict):
        matches = []
        for file in scan_files(self.sync.root):
            try:
                if parse_document(file.content).id == note.id:
                    matches.append(file)
            except ValueError:
                pass
        if len(matches) > 1:
            raise ContentError(409, "Duplicate note identities must be repaired first.")
        if matches:
            state.path = matches[0].path
            return matches[0]
        return read_file(self.sync.root, state.path or conflict.file_path or f"{note.id}.md")


def conflict_dict(conflict):
    return {column.name: getattr(conflict, column.name)
            for column in SyncConflict.__table__.columns}
