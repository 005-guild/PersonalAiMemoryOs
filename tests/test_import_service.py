"""Import transactions, conservative identities and side-effect-free previews."""

from contextlib import contextmanager
from pathlib import Path
from threading import RLock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import Knowledge, Source, SourceOrigin, SyncOperation, SyncState, utcnow
from app.repositories.database import Database
from app.repositories.imports import ImportRepository
from app.services.content import ContentService
from app.services.import_types import ImportItemResult, ImportUnavailable, ParsedZhihuItem
from app.services.importer import ImportService


@pytest.fixture
def importer(migrated_database: str):
    database = Database(migrated_database)
    database.initialize()
    try:
        yield database, ImportService(database, RLock())
    finally:
        database.dispose()


def item(index=0, external_id="123", resource_type="answer", **values) -> ParsedZhihuItem:
    url = (f"https://www.zhihu.com/question/1/answer/{external_id}"
           if resource_type == "answer" else f"https://zhuanlan.zhihu.com/p/{external_id}")
    return ParsedZhihuItem(index, resource_type, external_id, {
        "source_type": "zhihu", "title": "原始标题", "author": "作者",
        "url": url, "content": "完整原文\n第二行", **values,
    })


def counts(database) -> tuple[int, int]:
    with database.session() as session:
        return (session.scalar(select(func.count()).select_from(Source)),
                session.scalar(select(func.count()).select_from(SourceOrigin)))


def create_legacy(database, *, deleted=False, **values) -> str:
    with database.session() as session:
        source = Source(**{
            "source_type": "manual", "title": "手工资料", "content": "人工保留内容",
            "url": "http://zhihu.com/question/999/answer/123/?utm_source=legacy#part", **values,
        })
        if deleted:
            source.deleted_at = utcnow()
        session.add(source)
        session.commit()
        return source.id


def test_import_creates_source_and_origin_without_knowledge_or_vault(
    importer, isolated_project: Path,
) -> None:
    database, service = importer
    report = service.run([item()])
    assert report.created == report.processed == report.total == 1
    assert report.failed == 0
    result = report.items[0]
    assert result.source_id is not None
    assert result.version == 1
    with database.session() as session:
        source = session.get(Source, result.source_id)
        assert source.content == "完整原文\n第二行"
        assert source.source_type == "zhihu"
        origin = session.get(SourceOrigin, source.id)
        assert (origin.provider, origin.resource_type, origin.external_id) == ("zhihu", "answer", "123")
        assert origin.imported_at.endswith("+00:00")
        assert session.scalar(select(func.count()).select_from(Knowledge)) == 0
        assert session.scalar(select(func.count()).select_from(SyncState)) == 0
        assert session.scalar(select(func.count()).select_from(SyncOperation)) == 0
    assert not (isolated_project / "knowledge").exists()


def test_repeat_skips_changed_content_without_updating_source(importer) -> None:
    database, service = importer
    first = service.run([item()]).items[0]
    report = service.run([item(title="新标题", author="新作者", content="新原文")])
    result = report.items[0]
    assert result.status == "skipped"
    assert result.reason == "already_imported"
    assert result.source_id == first.source_id
    assert result.version == 1
    assert result.differing_fields == ["title", "author", "content"]
    assert counts(database) == (1, 1)
    with database.session() as session:
        assert session.get(Source, first.source_id).title == "原始标题"
        assert session.get(Source, first.source_id).version == 1


def test_origin_survives_manual_url_changes_and_soft_deletion(importer) -> None:
    database, service = importer
    first = service.run([item()]).items[0]
    with database.session() as session:
        source = session.get(Source, first.source_id)
        source.title = "人工标题"
        source.url = "https://example.com/edited-by-user"
        source.deleted_at = utcnow()
        session.commit()
        version = source.version
    result = service.run([item()]).items[0]
    assert result.reason == "deleted_source"
    assert result.source_id == first.source_id
    assert result.version == version
    assert result.differing_fields == ["title"]
    assert counts(database) == (1, 1)
    with database.session() as session:
        assert session.get(Source, first.source_id).deleted_at is not None


def test_answer_and_article_id_namespaces_are_separate(importer) -> None:
    database, service = importer
    report = service.run([item(), item(1, resource_type="article")])
    assert report.created == 2
    assert counts(database) == (2, 2)


def test_real_batch_duplicates_are_skipped_in_input_order(importer) -> None:
    database, service = importer
    report = service.run([item(0), item(1, title="不同标题"), item(2, external_id="456")])
    assert [result.index for result in report.items] == [0, 1, 2]
    assert [result.status for result in report.items] == ["created", "skipped", "created"]
    assert report.items[1].source_id == report.items[0].source_id
    assert report.items[1].differing_fields == ["title"]
    assert counts(database) == (2, 2)


def test_dry_run_simulates_duplicates_and_does_not_write(importer) -> None:
    database, service = importer
    report = service.run([item(0), item(1, content="Changed"), item(2, external_id="456")], dry_run=True)
    assert report.dry_run is True
    assert report.created == 0
    assert report.would_create == 2
    assert report.skipped == 1
    assert report.processed == report.total == 3
    assert report.items[1].reason == "duplicate_in_batch"
    assert report.items[1].differing_fields == ["content"]
    assert all(result.source_id is None for result in report.items)
    assert counts(database) == (0, 0)


@pytest.mark.parametrize("deleted", [False, True])
def test_legacy_match_skips_without_claiming_or_modifying_source(importer, deleted: bool) -> None:
    database, service = importer
    source_id = create_legacy(database, deleted=deleted)
    for dry_run in (True, False):
        result = service.run([item()], dry_run=dry_run).items[0]
        assert result.status == "skipped"
        assert result.reason == ("legacy_deleted" if deleted else "legacy_match")
        assert result.source_id == source_id
        assert result.matched_source_ids == [source_id]
        assert result.differing_fields == ["title", "author", "content"]
    assert counts(database) == (1, 0)
    with database.session() as session:
        source = session.get(Source, source_id)
        assert source.title == "手工资料"
        assert source.version == 1


def test_ambiguous_legacy_matches_are_reported_without_selecting_one(importer) -> None:
    database, service = importer
    first = create_legacy(database)
    second = create_legacy(database, deleted=True, url="https://www.zhihu.com/question/2/answer/123")
    result = service.run([item()]).items[0]
    assert result.status == "skipped"
    assert result.reason == "ambiguous_legacy_match"
    assert result.source_id is None
    assert set(result.matched_source_ids) == {first, second}
    assert counts(database) == (2, 0)


def test_legacy_identity_ignores_question_id_query_fragment_and_non_zhihu_urls(importer) -> None:
    database, service = importer
    legacy = create_legacy(database)
    create_legacy(database, url="https://example.com/question/1/answer/123")
    result = service.run([item(url="https://www.zhihu.com/question/777/answer/123")]).items[0]
    assert result.source_id == legacy
    assert counts(database) == (2, 0)


@pytest.mark.parametrize("resource_type", ["answer", "article"])
@pytest.mark.parametrize("existing_id,incoming_id", [("1234", "123"), ("123", "1234")])
def test_legacy_url_candidate_filter_does_not_merge_id_prefixes(
    importer, resource_type: str, existing_id: str, incoming_id: str,
) -> None:
    database, service = importer
    url = (f"https://www.zhihu.com/question/1/answer/{existing_id}"
           if resource_type == "answer" else f"https://zhuanlan.zhihu.com/p/{existing_id}")
    legacy_id = create_legacy(database, url=url)
    result = service.run([item(external_id=incoming_id, resource_type=resource_type)]).items[0]
    assert result.status == "created"
    assert result.source_id != legacy_id
    assert counts(database) == (2, 1)


def test_invalid_items_are_reported_without_interfering_with_valid_entries(importer) -> None:
    database, service = importer
    invalid = ImportItemResult(index=0, status="invalid", reason="validation_error")
    report = service.run([invalid, item(1)])
    assert report.invalid == report.created == 1
    assert report.processed == 2
    assert [result.index for result in report.items] == [0, 1]
    assert counts(database) == (1, 1)


def test_committed_items_are_reported_when_later_database_access_fails(importer, monkeypatch) -> None:
    database, service = importer
    original_session = database.session
    calls = 0

    def fail_second_session():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OperationalError("private-database-location", {}, Exception("secret"))
        return original_session()

    monkeypatch.setattr(database, "session", fail_second_session)
    with pytest.raises(ImportUnavailable) as error:
        service.run([item(0), item(1, external_id="456"), item(2, external_id="789")])
    report = error.value.report
    assert report.total == 3
    assert report.processed == 2
    assert report.created == report.failed == 1
    assert report.items[1].reason == "database_unavailable"
    assert "private-database-location" not in report.model_dump_json()
    assert "secret" not in report.model_dump_json()
    assert counts(database) == (1, 1)


def test_origin_insert_failure_rolls_back_source_as_well(importer, monkeypatch) -> None:
    database, service = importer

    def fail_insert(self, **values):
        raise IntegrityError("private-statement", {}, Exception("private-error"))

    monkeypatch.setattr(ImportRepository, "add_origin", fail_insert)
    with pytest.raises(ImportUnavailable):
        service.run([item()])
    assert counts(database) == (0, 0)


def test_unique_race_rechecks_identity_without_leaving_an_orphan_source(importer, monkeypatch) -> None:
    database, service = importer
    winner = service.run([item()]).items[0]
    original_origin = ImportRepository.origin
    origin_calls = 0

    def stale_first_lookup(repository, resource_type, external_id):
        nonlocal origin_calls
        origin_calls += 1
        if origin_calls == 1:
            return None  # Simulate the winner committing after our initial read.
        return original_origin(repository, resource_type, external_id)

    monkeypatch.setattr(ImportRepository, "origin", stale_first_lookup)
    result = service.run([item()]).items[0]
    assert result.status == "skipped"
    assert result.source_id == winner.source_id
    assert origin_calls == 2
    assert counts(database) == (1, 1)


def test_dry_run_checks_existing_sources_without_adding_origins(importer) -> None:
    database, service = importer
    existing = service.run([item()]).items[0]
    preview = service.run([item(title="Modified input"), item(1, external_id="456")], dry_run=True)
    assert preview.items[0].source_id == existing.source_id
    assert preview.items[0].differing_fields == ["title"]
    assert preview.would_create == preview.skipped == 1
    assert counts(database) == (1, 1)


def test_lock_and_session_are_released_between_items(importer) -> None:
    database, _ = importer

    class ObservedLock:
        def __init__(self):
            self.entries = self.exits = 0
            self.held = False

        def __enter__(self):
            assert not self.held
            self.held = True
            self.entries += 1

        def __exit__(self, *args):
            self.held = False
            self.exits += 1

    lock = ObservedLock()
    report = ImportService(database, lock).run([item(0), item(1, external_id="456")])
    assert report.created == 2
    assert lock.entries == lock.exits == 2
    assert lock.held is False
