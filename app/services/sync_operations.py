"""Write-ahead journal for recoverable Markdown file side effects."""

from sqlalchemy import select

from app.models import Knowledge, SyncOperation, utcnow
from app.services.files import FileChangedError, atomic_write, read_file, remove_file
from app.services.markdown import raw_hash, render_document
from app.services.sync_state import baseline, normalize_snapshot, snapshot, state_for


class OperationJournal:
    def __init__(self, root, conflict_handler):
        self.root = root
        self.conflict_handler = conflict_handler

    def queue(self, session, note, state, path, file, doc=None, kind="write"):
        content = render_document(doc) if doc is not None else None
        operation = SyncOperation(
            knowledge_id=note.id, kind=kind, path=path,
            expected_hash=file.hash if file else None,
            target_hash=raw_hash(content) if content is not None else None,
            target_content=content, previous_content=file.content if file else None,
            target_snapshot=snapshot(note), expected_version=note.version,
            status="pending",
        )
        session.add(operation)
        state.status = "pending"
        session.commit()  # The operation and the note must survive a failed file write.
        return operation

    def pending(self, session):
        return list(session.scalars(select(SyncOperation).where(
            SyncOperation.status.in_(["pending", "error"])
        ).order_by(SyncOperation.created_at, SyncOperation.id)))

    def execute(self, session, operation):
        note = session.get(Knowledge, operation.knowledge_id)
        if note is None:
            operation.status = "cancelled"
            session.commit()
            return
        state = state_for(session, note)
        try:
            current = read_file(self.root, operation.path)
            actual_hash = current.hash if current else None
            # A previous process may have completed the write but not its DB ack.
            if actual_hash == operation.target_hash:
                self._complete(session, operation, note, state)
                return
            if operation.kind == "identity" and note.deleted_at is not None:
                operation.status = "cancelled"
                session.commit()
                return
            if (operation.kind != "identity"
                    and note.version != operation.expected_version):
                operation.status = "cancelled"
                session.commit()
                return
            if actual_hash != operation.expected_hash:
                # Earlier, acknowledged writes can advance an API deletion's base.
                if (operation.kind == "delete" and actual_hash == state.file_hash):
                    operation.expected_hash = actual_hash
                else:
                    operation.status = "blocked"
                    self.conflict_handler(session, note, state, current,
                                          "file_changed_during_operation")
                    return
            operation.previous_content = current.content if current else None
            session.commit()
            if operation.kind == "delete":
                remove_file(self.root, operation.path, operation.expected_hash)
            else:
                atomic_write(self.root, operation.path, operation.target_content,
                             operation.expected_hash)
            self._complete(session, operation, note, state)
        except FileChangedError:
            operation.status = "blocked"
            self.conflict_handler(session, note, state,
                                  read_file(self.root, operation.path),
                                  "file_changed_during_operation")
        except OSError as exc:
            operation.status = "error"
            operation.error = type(exc).__name__
            state.status = "error"
            state.last_error = type(exc).__name__
            session.commit()
        except RuntimeError as exc:
            operation.status = "error"
            operation.error = type(exc).__name__
            state.status = "error"
            state.last_error = type(exc).__name__
            session.commit()

    @staticmethod
    def _complete(session, operation, note, state):
        target = normalize_snapshot(operation.target_snapshot)
        baseline(state, target, operation.target_hash, operation.path)
        if snapshot(note) != target:
            state.status = "pending"
        operation.status = "applied"
        operation.error = None
        operation.completed_at = utcnow()
        session.commit()
