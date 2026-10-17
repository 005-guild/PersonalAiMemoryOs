"""Explicit migrations, foreign keys and optimistic revision enforcement."""

from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.models import Knowledge, ProcessingRun, Source, SourceOrigin, SyncState, new_id, utcnow
from app.repositories.database import Database
from app.repositories.migrations import check_schema, migration_config, upgrade_database


def test_upgrade_creates_schema_and_preserves_data_on_repeat(sqlite_url: str) -> None:
    upgrade_database(sqlite_url)
    database = Database(sqlite_url)
    try:
        database.initialize()
        check_schema(database.engine)
        with database.session() as session:
            source = Source(source_type="manual", title="Original", content="Raw text")
            session.add(source)
            session.flush()
            note = Knowledge(source_id=source.id, title="Note", body="Body")
            session.add(note)
            session.flush()
            session.add(SyncState(knowledge_id=note.id))
            session.commit()
            note_id = note.id
    finally:
        database.dispose()

    upgrade_database(sqlite_url)
    try:
        database.initialize()
        check_schema(database.engine)
        with database.session() as session:
            note = session.get(Knowledge, note_id)
            assert note.body == "Body"
            assert note.version == 1
            assert session.get(SyncState, note_id).status == "pending"
    finally:
        database.dispose()


def test_schema_check_does_not_create_or_migrate_tables(sqlite_url: str) -> None:
    database = Database(sqlite_url)
    try:
        database.initialize()
        with pytest.raises(RuntimeError, match="schema"):
            check_schema(database.engine)
        assert inspect(database.engine).get_table_names() == []
    finally:
        database.dispose()


def test_schema_check_rejects_outdated_revision(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = '0000'"))
        with pytest.raises(RuntimeError, match="schema"):
            check_schema(database.engine)
    finally:
        database.dispose()


def test_schema_check_rejects_missing_table(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.engine.begin() as connection:
            connection.execute(text("DROP TABLE sync_states"))
        with pytest.raises(RuntimeError, match="schema"):
            check_schema(database.engine)
    finally:
        database.dispose()


def test_foreign_keys_apply_to_every_connection(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.engine.connect() as first, database.engine.connect() as second:
            assert first.scalar(text("PRAGMA foreign_keys")) == 1
            assert second.scalar(text("PRAGMA foreign_keys")) == 1
        with database.session() as session:
            session.add(Knowledge(title="Invalid link", source_id="missing"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        database.dispose()


def test_orm_revision_rejects_stale_session(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.session() as session:
            note = Knowledge(title="Initial")
            session.add(note)
            session.commit()
            note_id = note.id
        with database.session() as first, database.session() as second:
            current = first.get(Knowledge, note_id)
            stale = second.get(Knowledge, note_id)
            current.title = "Newer"
            first.commit()
            assert current.version == 2
            stale.title = "Must not overwrite"
            with pytest.raises(StaleDataError):
                second.commit()
            second.rollback()
    finally:
        database.dispose()


def test_explicit_upgrade_uses_only_selected_project_file(
    isolated_project: Path,
) -> None:
    selected = isolated_project / "selected" / "memory.db"
    upgrade_database(f"sqlite:///{selected.as_posix()}")
    assert selected.is_file()
    assert not (isolated_project / "data").exists()


def test_upgrade_0001_to_0002_preserves_content_and_sync_baseline(sqlite_url: str) -> None:
    database = Database(sqlite_url)
    baseline = {"title": "Existing", "body": "Do not replace", "deleted": False}
    try:
        database.initialize()
        with database.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "0001")
        with database.session() as session:
            source = Source(source_type="manual", title="Original", content="Preserved raw text")
            session.add(source)
            session.flush()
            note = Knowledge(source_id=source.id, title="Existing", body="Do not replace")
            session.add(note)
            session.flush()
            session.add(SyncState(knowledge_id=note.id, base=baseline, status="synced"))
            session.commit()
            source_id, note_id = source.id, note.id
        with pytest.raises(RuntimeError, match="schema"):
            check_schema(database.engine)
    finally:
        database.dispose()

    upgrade_database(sqlite_url)
    try:
        database.initialize()
        check_schema(database.engine)
        with database.session() as session:
            assert session.get(Source, source_id).content == "Preserved raw text"
            assert session.get(Source, source_id).version == 1
            assert session.get(Knowledge, note_id).body == "Do not replace"
            assert session.get(SyncState, note_id).base == baseline
            assert session.query(SourceOrigin).count() == 0
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(migration_config()).get_current_head()
    finally:
        database.dispose()


def test_upgrade_0002_to_head_preserves_sources_origins_and_knowledge(sqlite_url: str) -> None:
    database = Database(sqlite_url)
    try:
        database.initialize()
        with database.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "0002")
        with database.session() as session:
            source = Source(source_type="zhihu", title="旧来源", content="完整原文")
            session.add(source)
            session.flush()
            session.add(SourceOrigin(source_id=source.id, provider="zhihu", resource_type="answer", external_id="456"))
            note = Knowledge(source_id=source.id, title="旧笔记", body="已有笔记正文")
            session.add(note)
            session.flush()
            session.add(SyncState(knowledge_id=note.id, status="synced", base={"body": "已有笔记正文"}))
            session.commit()
            source_id, note_id = source.id, note.id
    finally:
        database.dispose()
    upgrade_database(sqlite_url)
    upgrade_database(sqlite_url)
    try:
        database.initialize()
        check_schema(database.engine)
        with database.session() as session:
            assert session.get(Source, source_id).content == "完整原文"
            assert session.get(SourceOrigin, source_id).external_id == "456"
            assert session.get(Knowledge, note_id).body == "已有笔记正文"
            assert session.get(SyncState, note_id).base == {"body": "已有笔记正文"}
            assert session.query(ProcessingRun).count() == 0
        with database.engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == ScriptDirectory.from_config(migration_config()).get_current_head()
    finally:
        database.dispose()


def test_processing_run_restricts_physical_source_and_adopted_knowledge_delete(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.session() as session:
            source = Source(source_type="manual", title="Source", content="Raw")
            session.add(source)
            session.flush()
            note = Knowledge(source_id=source.id, title="Adopted note")
            session.add(note)
            session.flush()
            run = ProcessingRun(source_id=source.id, source_version=1, source_snapshot={"id": source.id},
                                input_hash="a" * 64, profile_id="test", protocol="openai_chat", model="model",
                                config_fingerprint="b" * 64, prompt_version="test", prompt_hash="c" * 64,
                                output_schema_version=1, status="adopted", adopted_knowledge_id=note.id)
            session.add(run)
            session.commit()
            source_id, note_id = source.id, note.id
        for model, record_id in ((Source, source_id), (Knowledge, note_id)):
            with database.session() as session:
                session.delete(session.get(model, record_id))
                with pytest.raises(IntegrityError):
                    session.commit()
                session.rollback()
                assert session.get(model, record_id) is not None
    finally:
        database.dispose()


def test_upgrade_0003_to_0004_preserves_processing_and_content(sqlite_url: str) -> None:
    database = Database(sqlite_url)
    database.initialize()
    try:
        with database.engine.begin() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "0003")
        with database.session() as session:
            source = Source(source_type="manual", title="保留来源", content="原始内容")
            session.add(source)
            session.flush()
            note = Knowledge(title="保留笔记", body="正文", source_id=source.id)
            session.add(note)
            session.flush()
            run_id = new_id()
            historical = Table("processing_runs", MetaData(), autoload_with=session.connection())
            session.execute(historical.insert().values(
                id=run_id, version=1, created_at=utcnow(), updated_at=utcnow(), started_at=utcnow(),
                source_id=source.id, source_version=1, source_snapshot={"title": source.title},
                input_hash="a" * 64, profile_id="old-profile", protocol="openai_chat", model="old-model",
                config_fingerprint="b" * 64, prompt_version="knowledge-v1", prompt_hash="c" * 64,
                output_schema_version=1, status="adopted", adopted_knowledge_id=note.id,
                result={"summary": "已有摘要"}, proposal={"body": "正文"},
            ))
            session.commit()
            source_id, note_id = source.id, note.id
    finally:
        database.dispose()
    upgrade_database(sqlite_url)
    upgrade_database(sqlite_url)
    database.initialize()
    try:
        check_schema(database.engine)
        with database.session() as session:
            assert session.get(Source, source_id).content == "原始内容"
            assert session.get(Knowledge, note_id).body == "正文"
            run = session.get(ProcessingRun, run_id)
            assert run.status == "adopted" and run.adopted_knowledge_id == note_id
            assert run.result == {"summary": "已有摘要"}
        assert {"rag_index_generations", "rag_note_index_states", "rag_index_jobs"}.issubset(
            inspect(database.engine).get_table_names()
        )
    finally:
        database.dispose()


def test_source_origin_constraints_and_restricted_physical_delete(migrated_database: str) -> None:
    database = Database(migrated_database)
    try:
        database.initialize()
        with database.session() as session:
            first = Source(source_type="zhihu_answer", title="Answer")
            second = Source(source_type="zhihu_article", title="Article")
            session.add_all([first, second])
            session.flush()
            session.add_all([
                SourceOrigin(source_id=first.id, provider="zhihu", resource_type="answer", external_id="123"),
                SourceOrigin(source_id=second.id, provider="zhihu", resource_type="article", external_id="123"),
            ])
            session.commit()
            first_id = first.id
        with database.session() as session:
            duplicate = Source(source_type="zhihu_answer", title="Duplicate")
            session.add(duplicate)
            session.flush()
            duplicate_id = duplicate.id
            session.add(SourceOrigin(source_id=duplicate.id, provider="zhihu", resource_type="answer", external_id="123"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.get(Source, duplicate_id) is None
            assert session.query(SourceOrigin).count() == 2
        with database.session() as session:
            session.add(SourceOrigin(source_id="missing", provider="zhihu", resource_type="answer", external_id="456"))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            session.delete(session.get(Source, first_id))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            assert session.get(Source, first_id) is not None
    finally:
        database.dispose()
