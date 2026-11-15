"""Unified reading includes ordinary notes without weakening collection guards."""
from sqlalchemy import select
from fastapi.testclient import TestClient
from app.main import create_app
from app.models import Knowledge, Source, SyncState
from app.services.content import ContentService
from app.repositories.reading_all import AllReadingRepository
from test_reading import reading
from test_collection_organization import organization


def test_union_filters_sources_and_pending_notes(reading):
    view, service, model, ids, _, _ = reading
    with service.store.transaction() as session:
        content = ContentService(session)
        sources = [content.create_source({'source_type': 'manual', 'title': '独有来源', 'content': '来源短词百分号%_'}) for _ in range(2)]
        note = content.create_knowledge({'title': '普通笔记', 'summary': '简短', 'body': '正文关键词', 'category': '技术/数据库',
                                        'tags': ['普通'], 'source_ids': [s['id'] for s in sources]})
    assert view.overview()['total'] == 4
    assert view.overview(scope='all')['total'] == 5
    assert view.overview(scope='other')['total'] == 1
    for q in ('普通', '正文关键词', '来源短词', '%_'):
        result = view.notes(scope='other', q=q)
        assert result['total'] == 1 and result['items'][0]['knowledge_id'] == note['id']
    assert view.notes(scope='other', tag='普通', category='技术/数据库')['total'] == 1
    detail = view.detail(note['id'], scope='all')
    assert len(detail['sources']) == 2 and detail['original'] is None
    assert detail['capabilities'] == {'quality': False} and detail['sync_status'] == 'pending'
    pages = [view.notes(scope='all', limit=2, offset=o)['items'] for o in (0, 2, 4)]
    assert len({row['knowledge_id'] for page in pages for row in page}) == 5
    with service.store.transaction() as session:
        session.get(SyncState, note['id']).status = 'conflict'
    assert view.overview(scope='all')['total'] == 4
    assert view.overview(scope='all')['unavailable_count'] == 1


def test_management_projection_and_scope_api(reading, settings):
    view, service, _, ids, _, _ = reading
    app = create_app(settings); app.state.organization = service
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.get('/api/v1/reading/overview?scope=all').json()['total'] == 4
    assert client.get('/api/v1/reading/notes?scope=invalid').status_code == 422
    rows = client.get('/api/v1/collection-organization/records?limit=2').json()
    assert rows['total'] == 4 and len(rows['items']) == 2
    assert not {'result', 'original', 'input_hash'} & rows['items'][0].keys()
    detail = client.get('/api/v1/collection-organization/records/'+rows['items'][0]['id']).json()
    assert detail['original']['content']
    jobs = client.get('/api/v1/collection-organization/jobs?limit=1').json()
    assert jobs['total'] >= 1 and 'selection' not in jobs['items'][0]
    assert client.get('/api/v1/collection-organization/jobs/'+jobs['items'][0]['id']).status_code == 200
    assert client.get('/api/v1/collection-organization/records/missing').status_code == 404
    assert client.get('/api/v1/collection-organization/records', headers={'Host':'evil.example'}).status_code == 403
