"""0004 upgrades add provenance without rewriting Markdown or content versions."""

from threading import RLock

from alembic import command
from sqlalchemy import select

from app.config import Settings
from app.models import Knowledge, KnowledgeSource, Source, SyncState, SyncVault, utcnow
from app.repositories.database import Database
from app.repositories.migrations import migration_config, upgrade_database
from app.repositories.rag import hash_note
from app.services.markdown import NoteDocument, content_hash, raw_hash, render_document
from app.services.sync import Synchronizer
from app.services.sync_state import file_snapshot


def test_0004_backfill_preserves_single_source_file_baseline_versions_and_cache_hash(sqlite_url, isolated_project):
    database = Database(sqlite_url)
    database.initialize()
    try:
        with database.engine.begin() as connection:
            configuration = migration_config()
            configuration.attributes["connection"] = connection
            command.upgrade(configuration, "0004")
        with database.session() as session:
            source = Source(title="legacy source", source_type="manual", content="original")
            session.add(source); session.flush()
            note = Knowledge(source_id=source.id, title="legacy", body="完整旧正文\n", summary="summary")
            deleted = Knowledge(source_id=source.id, title="deleted", deleted_at=utcnow())
            standalone = Knowledge(title="standalone", body="no source", deleted_at=utcnow())
            session.add_all([note, deleted, standalone]); session.flush()
            doc = NoteDocument(id=note.id, source_id=source.id, title=note.title, body=note.body, summary=note.summary)
            rendered = render_document(doc)
            base = file_snapshot(doc)
            session.add(SyncState(knowledge_id=note.id, path="legacy.md", base=base,
                                  base_hash=content_hash(base), file_hash=raw_hash(rendered), status="synced"))
            session.add(SyncVault(id=1, token="legacy-vault", initialized=True))
            session.commit()
            source_id, note_id, deleted_id, standalone_id = source.id, note.id, deleted.id, standalone.id
            before_hash = hash_note({field: getattr(note, field) for field in ("title", "body", "summary", "category", "tags", "concepts")})
        root = isolated_project / "knowledge"
        root.mkdir()
        (root / ".memory-os-vault").write_text("legacy-vault", encoding="utf-8")
        path = root / "legacy.md"
        path.write_bytes(rendered.encode("utf-8"))
        original_bytes = path.read_bytes()
    finally:
        database.dispose()
    upgrade_database(sqlite_url)
    upgrade_database(sqlite_url)
    database.initialize()
    try:
        with database.session() as session:
            rows = list(session.scalars(select(KnowledgeSource)))
            assert {(row.knowledge_id, row.source_id, row.position) for row in rows} == {
                (note_id, source_id, 0), (deleted_id, source_id, 0)}
            note = session.get(Knowledge, note_id)
            assert note.source_ids == [source_id] and note.version == 1
            assert session.get(Knowledge, deleted_id).version == 1
            assert session.get(Knowledge, standalone_id).source_ids == []
            assert session.get(Source, source_id).version == 1
            assert hash_note({**{field: getattr(note, field) for field in ("title", "body", "summary", "category", "tags", "concepts")},
                              "source_ids": note.source_ids}) == before_hash
            state = session.get(SyncState, note_id)
            assert state.base == base and state.base_hash == content_hash(base)
        settings = Settings(runtime_root=isolated_project, database_url=sqlite_url, _env_file=None, sync_enabled=False)
        synchronizer = Synchronizer(database, settings, RLock())
        for _ in range(3):
            status = synchronizer.run_once(now=100)
            assert status["last_error"] is None and not status["issues"]
        assert path.read_bytes() == original_bytes
        with database.session() as session:
            state = session.get(SyncState, note_id)
            assert state.base == base and state.base_hash == content_hash(base)
            assert session.get(Knowledge, note_id).version == 1
    finally:
        database.dispose()
