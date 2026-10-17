"""Complete vault scans and orchestration of note reconciliation."""

import logging
import time
from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import Knowledge, SyncOperation, SyncState, SyncVault, new_id, utcnow
from app.services.files import atomic_write, read_file, scan_files
from app.services.markdown import parse_document
from app.services.content import ContentService
from app.services.sync_operations import OperationJournal
from app.services.sync_reconcile import NoteReconciler
from app.services.sync_state import (
    EDITABLE, document, open_conflict, record_conflict, source_available, state_for,
)

logger = logging.getLogger(__name__)
MARKER = ".memory-os-vault"


class Synchronizer:
    def __init__(self, database, settings, lock):
        self.database, self.settings, self.lock = database, settings, lock
        self.root = settings.knowledge_path
        self.journal = OperationJournal(self.root, record_conflict)
        self.reconciler = NoteReconciler(self.journal, settings.deletion_grace)
        self.last_scan_at = None
        self.last_error = None
        self.issues = []
        self.worker_running = False
        self._observed = {}
        self._fresh_process = True

    def run_once(self, *, now=None):
        with self.lock:
            self.issues, self.last_error = [], None
            try:
                with self.database.session() as session:
                    self._prepare_vault(session)
                    files = scan_files(self.root)
                    if self._fresh_process:
                        for state in session.scalars(select(SyncState)):
                            state.missing_since, state.missing_count = None, 0
                        session.commit()
                        self._fresh_process = False
                    self._scan(session, files, time.time() if now is None else now)
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.error("Synchronization cycle failed (%s).", type(exc).__name__)
            self.last_scan_at = utcnow()
            return self.status()

    def _prepare_vault(self, session):
        vault = session.get(SyncVault, 1)
        if vault is None:
            vault = SyncVault(id=1, token=new_id(), initialized=False)
            session.add(vault)
            session.commit()
        if not self.root.exists():
            if vault.initialized:
                raise RuntimeError("Knowledge directory is missing.")
            self.root.mkdir(parents=True)
        marker = read_file(self.root, MARKER)
        if marker is None:
            if vault.initialized:
                raise RuntimeError("Knowledge directory marker is missing.")
            atomic_write(self.root, MARKER, vault.token, None)
        elif marker.content != vault.token:
            raise RuntimeError("Knowledge directory marker does not match.")
        if not vault.initialized:
            vault.initialized = True
            session.commit()

    def _scan(self, session, files, now):
        by_path = {file.path: file for file in files}
        stable, unstable = self._stable_files(files)
        documents, identities = {}, defaultdict(list)
        invalid = set()
        for file in stable:
            try:
                doc = parse_document(file.content)
                documents[file.path] = doc
                if doc.id:
                    identities[doc.id].append(file)
            except ValueError:
                invalid.add(file.path)
                self._issue(file.path, "invalid_markdown")
        duplicates = {key for key, matches in identities.items() if len(matches) > 1}
        for identity in duplicates:
            for file in identities[identity]:
                self._issue(file.path, "duplicate_id")
        notes = list(session.scalars(select(Knowledge)))
        known = {note.id: note for note in notes}
        tracked = {state.path: state.knowledge_id for state in
                   session.scalars(select(SyncState)) if state.path}
        blocked = set(duplicates)
        for file in stable:
            doc = documents.get(file.path)
            owner = tracked.get(file.path)
            if owner and (doc is None or doc.id != owner):
                claim = session.scalars(select(SyncOperation).where(
                    SyncOperation.knowledge_id == owner,
                    SyncOperation.kind == "identity", SyncOperation.path == file.path,
                    SyncOperation.status.in_(["pending", "error"]),
                )).first()
                if doc is not None and doc.id is None and claim is not None:
                    continue  # Resume the durable UUID assignment, not a new import.
                # A legitimate rename may reuse a path; find both identities first.
                if owner not in identities:
                    blocked.add(owner)
                    self._issue(file.path, "identity_changed_at_tracked_path")
        for identity, matches in identities.items():
            if identity not in known:
                self._issue(matches[0].path, "unknown_id")
            elif identity not in duplicates:
                state_for(session, known[identity]).path = matches[0].path
        session.commit()
        processed = self._recover(session, identities, blocked, unstable, invalid, by_path)
        deletion_allowed = not unstable and not invalid and not duplicates and not self.issues
        for note in notes:
            if note.id in processed:
                continue
            state = state_for(session, note)
            if note.id in blocked:
                state.status, state.last_error = "error", "invalid_or_duplicate_identity"
                session.commit()
                continue
            matches = identities.get(note.id, [])
            file = matches[0] if matches else None
            if file is None and state.path in by_path:
                # A partially saved or unidentified file is never treated as absence.
                continue
            self.reconciler.reconcile(
                session, note, state, file,
                documents[file.path] if file else None, now, deletion_allowed,
            )
        self._import_new(session, stable, documents, tracked)

    def _stable_files(self, files):
        observations, stable, unstable = {}, [], set()
        for file in files:
            previous = self._observed.get(file.path)
            count = previous[1] + 1 if previous and previous[0] == file.hash else 1
            observations[file.path] = (file.hash, count)
            if count >= 2:
                stable.append(file)
            else:
                unstable.add(file.path)
        self._observed = observations
        return stable, unstable

    def _recover(self, session, identities, blocked, unstable, invalid, by_path):
        processed = set()
        for operation in self.journal.pending(session):
            if (operation.knowledge_id in blocked or operation.path in unstable
                    or operation.path in invalid
                    or open_conflict(session, operation.knowledge_id) is not None
                    or (operation.path not in by_path and unstable)):
                continue
            matches = identities.get(operation.knowledge_id, [])
            if len(matches) == 1 and operation.kind != "identity":
                operation.path = matches[0].path
                session.commit()
            self.journal.execute(session, operation)
            processed.add(operation.knowledge_id)
        return processed

    def _import_new(self, session, files, documents, tracked):
        pending_identity = session.scalars(select(SyncOperation).where(
            SyncOperation.kind == "identity",
            SyncOperation.status.in_(["pending", "error", "blocked"]),
        )).first()
        for file in files:
            doc = documents.get(file.path)
            if doc is None or doc.id is not None or file.path in tracked:
                continue
            if pending_identity is not None:
                self._issue(file.path, "identity_recovery_required")
                continue
            if not source_available(session, doc.association_ids):
                self._issue(file.path, "invalid_source")
                continue
            created = ContentService(session).create_knowledge({"source_ids": doc.association_ids,
                        **{key: getattr(doc, key) for key in EDITABLE}})
            note = session.get(Knowledge, created["id"])
            state = state_for(session, note)
            state.path, state.file_hash = file.path, file.hash
            operation = self.journal.queue(session, note, state, file.path, file,
                                           document(note), "identity")
            self.journal.execute(session, operation)
            if operation.status != "applied":
                pending_identity = operation

    def _issue(self, path, code):
        self.issues.append({"path": path, "code": code})

    def status(self):
        with self.lock:
            try:
                with self.database.session() as session:
                    states = list(session.scalars(select(SyncState)))
                    counts = Counter(state.status for state in states)
                    notes = [{"knowledge_id": state.knowledge_id, "path": state.path,
                              "status": state.status, "last_error": state.last_error,
                              "last_synced_at": state.last_synced_at} for state in states]
            except Exception as exc:
                self.last_error = type(exc).__name__
                counts, notes = {}, []
            return {"enabled": self.settings.sync_enabled,
                    "running": self.worker_running, "last_scan_at": self.last_scan_at,
                    "last_error": self.last_error, "counts": dict(counts),
                    "issues": list(self.issues), "notes": notes}
