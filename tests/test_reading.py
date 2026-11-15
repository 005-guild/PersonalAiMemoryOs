"""Read projections, identity boundaries and zero-mutation collection browsing."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from app.main import create_app
from app.models import Knowledge, OrganizationItem, OrganizationControl, SyncState
from app.services.content import ContentError, ContentService
from app.services.reading import ReadingService
from app.services.organization.search import keyword_search
from test_collection_organization import organization, approved, run, article, PNG


@pytest.fixture
def reading(organization):
    service, model, source, output = organization
    approved(service, source, 4)
    run(service, 'all')
    with service.store.transaction() as session:
        ids = list(session.scalars(select(Knowledge.id).order_by(Knowledge.id)))
        for index, identifier in enumerate(ids):
            ContentService(session).update_knowledge(identifier, 1, {
                'title': ['甲：实践方法', '乙：AI%', '丙：原文测试', '丁：其他'][index],
                'summary': '归纳概述', 'category': ['技术/人工智能', '技术/数据库', '技术扩展/工具', '生活/经验'][index],
                'tags': [['实践', '共同'], ['AI%', '共同'], ['工具'], ['生活']][index],
                'body': '## 要点\n人工编辑后的正文。OnlyInBodyTest。\n文字中的100%_!与中文短词。',
            })
            session.get(Knowledge, identifier).updated_at = ['2026-10-31T16:30:00+00:00',
                '2026-10-15T12:00:00+00:00', '2026-09-01T12:00:00+00:00', '2026-08-01T12:00:00+00:00'][index]
    service.publication.refresh(service.store.read()['config'])
    return ReadingService(service.store), service, model, ids, source, output


def test_overview_filters_and_bounded_projection(reading):
    view, service, _, ids, _, _ = reading
    overview = view.overview()
    assert overview['total'] == 4 and overview['unavailable_count'] == 0
    assert next(x for x in overview['topics'] if x['name'] == '技术')['count'] == 2
    assert overview['months'] == ['2026-11', '2026-10', '2026-09', '2026-08']
    assert view.notes(topic='技术')['total'] == 2  # Does not include 技术扩展.
    assert view.notes(topic='技术', category='技术/数据库', tag='共同', updated_month='2026-10')['total'] == 1
    assert view.notes(topic='技术', tag='共同', updated_month='2026-11')['items'][0]['knowledge_id'] == ids[0]
    assert view.notes(tag='AI%')['total'] == 1
    assert view.notes(category='无/结果')['total'] == 0
    first = view.notes(limit=2)
    second = view.notes(limit=2, offset=2)
    assert first['total'] == second['total'] == 4
    assert set(x['knowledge_id'] for x in first['items']).isdisjoint(x['knowledge_id'] for x in second['items'])
    assert len({x['knowledge_id'] for x in first['items'] + second['items']}) == 4
    titles = [x['title'] for x in view.notes(sort='title_asc')['items']]
    assert titles == sorted(titles)
    assert all(not {'body', 'content', 'snapshot', 'images'} & item.keys() for item in first['items'])
    assert view.notes(q='onlyinbodytest')['items'][0]['match_section'] == 'original'
    for query in ['人工', '中', '100%_!', '%', '_', '"', 'OnlyInBodyTest', '测试文章']:
        assert view.notes(q=query)['total'] == keyword_search(service.store, query)['total']
    assert view.notes(q='测试文章')['items'][0]['match_section'] == 'title'


def test_all_read_requests_preserve_files_rows_and_calls(reading):
    view, service, model, ids, source, output = reading
    def database():
        with service.store.transaction() as session:
            return '\n'.join(session.connection().connection.driver_connection.iterdump())
    before = database()
    files = {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
             for root in (source, output) for p in root.rglob('*') if p.is_file()}
    calls = len(model.calls)
    statements = []
    def record(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'REPLACE')):
            statements.append(statement)
    event.listen(service.store.database.engine, 'before_cursor_execute', record)
    try:
        view.overview(); view.notes(q='人工'); view.notes(updated_month='2026-11')
        detail = view.detail(ids[0])
        assert detail['note']['title'] == '甲：实践方法'
        assert '人工编辑后的正文' in detail['note']['body']
        assert detail['original']['title'].startswith('测试文章')
        assert '人工编辑后的正文' not in detail['original']['content']
    finally:
        event.remove(service.store.database.engine, 'before_cursor_execute', record)
    assert not statements
    assert database() == before and len(model.calls) == calls
    assert files == {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                     for root in (source, output) for p in root.rglob('*') if p.is_file()}


def test_reading_does_not_wait_for_background_filesystem_scan(reading):
    view, service, _, ids, _, _ = reading
    def browse():
        return view.overview()['total'], view.notes()['total'], view.detail(ids[0])['note']['id']
    with ThreadPoolExecutor(max_workers=1) as executor:
        # Simulate a background scan that owns the shared lock. An independent
        # HTTP reader must still see committed data before that scan completes.
        with service.store.lock:
            assert executor.submit(browse).result(timeout=2) == (4, 4, ids[0])


def test_local_image_read_does_not_wait_for_background_scan(reading, settings):
    _, service, _, _, _, output = reading
    name = hashlib.sha256(PNG).hexdigest() + '.png'
    (output / 'assets').mkdir(exist_ok=True)
    (output / 'assets' / name).write_bytes(PNG)
    app = create_app(settings); app.state.organization = service
    client = TestClient(app, base_url='http://127.0.0.1')
    with ThreadPoolExecutor(max_workers=1) as executor:
        with service.store.lock:
            response = executor.submit(client.get, '/api/v1/collection-organization/assets/' + name).result(timeout=2)
            assert response.status_code == 200 and response.content == PNG


@pytest.mark.parametrize('problem', ['deleted', 'source_changed', 'conflict', 'version', 'missing_index'])
def test_unavailable_items_have_consistent_counts_and_detail_errors(reading, problem):
    view, service, _, ids, _, _ = reading
    with service.store.transaction() as session:
        note = session.get(Knowledge, ids[0])
        item = session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id == note.id))
        if problem == 'deleted': note.deleted_at = '2026-11-15T00:00:00+00:00'
        elif problem == 'source_changed': item.error = problem
        elif problem == 'conflict': session.get(SyncState, note.id).status = 'conflict'
        elif problem == 'version': note.title = '尚未导出'
        else: session.execute(text('DELETE FROM organization_fts WHERE item_id=:id'), {'id': item.id})
    assert view.overview()['total'] == view.notes()['total'] == 3
    assert view.overview()['unavailable_count'] == (0 if problem == 'deleted' else 1)
    with pytest.raises(ContentError) as caught: view.detail(ids[0])
    assert caught.value.status_code == (404 if problem == 'deleted' else 409)
    with pytest.raises(ContentError) as caught: view.detail(str(uuid4()))
    assert caught.value.status_code == 404


def test_original_images_are_local_ordered_and_missing_images_do_not_repair(organization):
    service, model, source, output = organization
    source.mkdir(); (source / 'photo.png').write_bytes(PNG)
    article(source, 1, '原文依据。\n' + '可核对的文字。' * 60 + '\n![配图](photo.png)')
    service.store.scan(); job = run(service, 'sample'); service.store.approve(job['id']); run(service, 'all')
    view = ReadingService(service.store); identifier = view.notes()['items'][0]['knowledge_id']
    detail = view.detail(identifier)
    assert detail['images'][0]['reference'] == 'photo.png'
    assert detail['images'][0]['url'].startswith('/api/v1/collection-organization/assets/')
    assert not detail['images'][0]['missing']
    for image in (output / 'assets').iterdir(): image.unlink()
    assert view.detail(identifier)['images'][0]['missing']
    assert not list((output / 'assets').iterdir())
    assert ReadingService._images([{'reference': 'x', 'hash': '../../bad'}], str(output))[0]['missing']


def test_empty_reading_never_initializes_control(organization):
    service, _, _, _ = organization
    with service.store.transaction() as session:
        session.delete(session.get(OrganizationControl, 1))
    view = ReadingService(service.store)
    assert view.overview()['total'] == 0 and view.notes()['total'] == 0
    with service.store.transaction() as session:
        assert session.get(OrganizationControl, 1) is None


def test_api_validation_and_loopback_boundary(reading, settings):
    _, service, _, ids, _, _ = reading
    app = create_app(settings); app.state.organization = service
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.get('/api/v1/reading/overview').json()['total'] == 4
    assert client.get('/api/v1/reading/notes', params={'topic': '技术'}).json()['total'] == 2
    assert client.get('/api/v1/reading/notes/' + ids[0]).status_code == 200
    for params in [{'limit': 101}, {'offset': -1}, {'sort': 'random'}, {'updated_month': '2026-13'}, {'q': 'a' * 2001}]:
        assert client.get('/api/v1/reading/notes', params=params).status_code == 422
    assert client.get('/api/v1/reading/notes/invalid').status_code == 422
    assert client.get('/api/v1/reading/overview', headers={'Host': 'evil.example'}).status_code == 403
