"""Reconcile one identified note against its common synchronization base."""

from app.models import utcnow
from app.services.markdown import content_hash
from app.services.source_associations import association_ids
from app.services.sync_state import (
    apply_file, baseline, document, file_snapshot, open_conflict,
    record_conflict, snapshot, source_available,
)


class NoteReconciler:
    def __init__(self, journal, deletion_grace):
        self.journal = journal
        self.deletion_grace = deletion_grace

    def reconcile(self, session, note, state, file, doc, now, deletion_allowed):
        if open_conflict(session, note.id) is not None:
            record_conflict(session, note, state, file, "concurrent_changes")
            return
        if file is None:
            self._missing(session, note, state, now, deletion_allowed)
            return
        state.missing_since, state.missing_count = None, 0
        previous_sources = association_ids(state.base) if state.base else note.source_ids
        if doc.association_ids not in (previous_sources, note.source_ids):
            self._error(session, state, "source_ids_are_managed_by_api" if doc.schema_version == 2 else "source_id_is_managed_by_api")
            return
        if not source_available(session, note.source_ids):
            self._error(session, state, "source_is_deleted")
            return
        current, incoming = snapshot(note), file_snapshot(doc)
        if note.deleted_at is not None:
            if state.base and state.base.get("deleted"):
                apply_file(note, doc)
                note.deleted_at = None
                session.flush()
                if note.source_ids != doc.association_ids:
                    self._write(session, note, state, file, file.path)
                else:
                    baseline(state, snapshot(note), file.hash, file.path)
                    session.commit()
            else:
                record_conflict(session, note, state, file, "delete_vs_edit")
            return
        if current == incoming:
            baseline(state, current, file.hash, file.path)
            session.commit()
            return
        old_hash = state.base_hash
        db_changed = old_hash is None or content_hash(current) != old_hash
        file_changed = old_hash is None or content_hash(incoming) != old_hash
        if db_changed and file_changed:
            record_conflict(session, note, state, file, "concurrent_changes")
        elif db_changed:
            self._write(session, note, state, file, file.path)
        else:
            apply_file(note, doc)
            session.flush()
            # Keep a newly changed API association, never import it from Markdown.
            if note.source_ids != doc.association_ids:
                self._write(session, note, state, file, file.path)
            else:
                baseline(state, snapshot(note), file.hash, file.path)
                session.commit()

    def _missing(self, session, note, state, now, deletion_allowed):
        if note.deleted_at is not None:
            if state.base is None or not state.base.get("deleted"):
                baseline(state, snapshot(note), None, state.path or f"{note.id}.md")
            else:
                # No file exists to acknowledge a new Source association. Retain
                # the last file metadata so an archived copy can still be restored.
                state.status = "deleted"
                state.missing_since, state.missing_count = None, 0
            session.commit()
            return
        if state.base is None or state.base.get("deleted"):
            if not source_available(session, note.source_ids):
                self._error(session, state, "source_is_deleted")
                return
            self._write(session, note, state, None, state.path or f"{note.id}.md")
            return
        if not deletion_allowed:
            state.missing_since, state.missing_count = None, 0
            session.commit()
            return
        if snapshot(note) != state.base:
            record_conflict(session, note, state, None, "edit_vs_file_delete")
            return
        state.missing_since = now if state.missing_since is None else state.missing_since
        state.missing_count += 1
        state.status = "missing"
        if state.missing_count >= 2 and now - state.missing_since >= self.deletion_grace:
            note.deleted_at = utcnow()
            session.flush()
            baseline(state, snapshot(note), None, state.path)
        session.commit()

    def _write(self, session, note, state, file, path):
        operation = self.journal.queue(session, note, state, path, file, document(note))
        self.journal.execute(session, operation)

    @staticmethod
    def _error(session, state, error):
        state.status, state.last_error = "error", error
        session.commit()
