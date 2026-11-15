"""Normal entry points, adoption conflicts and shared monthly accounting."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.models import Knowledge, OrganizationItem, OrganizationJob
from app.services.content import ContentService, ContentError
from app.services.organization.contracts import OrganizationError
from app.services.organization.quality import QualityService
from test_collection_organization import organization, approved, run, article


def detailed(text):
    return {'summary':'作者强调通过实践理解人工智能。','overview':'文章介绍方法与实践之间的关系。',
        'points':[{'heading':'实践检验','detail':'作者认为方法需要实践检验。','evidence_ids':['Q1']}],
        'conditions':'原文属于经验介绍。','conclusion':'作者建议理解方法适用条件。',
        'source_quotes':[{'id':'Q1','quote':text[:20]}],'image_evidence_ids':[]}


def install_model(service):
    calls=[]
    async def generate(resolved,system,user,**kwargs):
        data=json.loads(user);calls.append(data)
        result=detailed(data.get('content') or data['parts'][0]['quotes'][0])
        if 'categories' in data:
            result.update(title='实践理解人工智能',category=data['categories'][0],tags=['方法','实践','学习'])
        return SimpleNamespace(text=json.dumps(result),usage={'input_tokens':100,'output_tokens':100})
    service.calls.client=SimpleNamespace(generate=generate)
    return calls


def test_candidate_adoption_is_version_checked_cached_and_idempotent(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    calls=install_model(service)
    with service.store.transaction() as session:
        note=session.scalar(select(Knowledge));identifier=note.id
    quality=QualityService(service)
    job=quality.start(identifier,1);assert service._next()==job['id']
    asyncio.run(service.run_job(job['id']))
    view=quality.view(identifier);candidate=view['candidate']
    assert candidate and len(calls)==1
    assert quality.start(identifier,1)['status']=='ready'
    quality.adopt(identifier,1,candidate['id'])
    assert quality.view(identifier)['current']['version']==2
    quality.adopt(identifier,1,candidate['id'])
    assert len(calls)==1
    with service.store.transaction() as session:
        assert session.scalar(select(OrganizationItem)).result['quality_previous']['version']==1
    job=quality.start(identifier,2);service._next();asyncio.run(service.run_job(job['id']))
    with service.store.transaction() as session:
        ContentService(session).update_knowledge(identifier,2,{'body':'人工编辑'})
    candidate=quality.view(identifier)['candidate']
    assert quality.view(identifier)['stale']
    with pytest.raises(ContentError):quality.adopt(identifier,2,candidate['id'])
    assert len(calls)==1  # Same model input reuses the received response.


def test_new_article_uses_detailed_contract_in_one_request(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    calls=install_model(service)
    with service.store.transaction() as session:
        control=service.store.control(session);control['quality_enabled']=True;service.store.set_control(session,control)
    article(source,2);service.store.scan()
    assert run(service,'all')['status']=='completed'
    assert len(calls)==1
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem).where(OrganizationItem.identity=='article:2'))
        assert item.result['detail']['points']
        assert '## 文章概述' in session.get(Knowledge,item.knowledge_id).body


def test_shared_external_costs_block_before_paid_request(organization):
    from datetime import datetime,timezone,timedelta
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    calls=install_model(service)
    with service.store.transaction() as session:
        note=session.scalar(select(Knowledge));identifier=note.id
        control=service.store.control(session)
        period=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m')
        control['external_costs']=[{'period':period,'accounted_micros':10_000_000}]
        service.store.set_control(session,control)
    quality=QualityService(service);job=quality.start(identifier,1)
    service._next();asyncio.run(service.run_job(job['id']))
    assert not calls
    assert next(row for row in service.store.read()['jobs'] if row['id']==job['id'])['status']=='paused'


def test_protected_quality_and_topic_api_entrypoints(organization):
    from fastapi.testclient import TestClient
    from app.main import create_app
    service,_,source,_=organization
    approved(service,source);run(service,'all');install_model(service)
    with service.store.transaction() as session:identifier=session.scalar(select(Knowledge.id))
    from app.config import Settings
    app=create_app(Settings(_env_file=None,runtime_root=service.store.root,
        database_url=service.store.database.url.render_as_string(),sync_enabled=False))
    from unittest.mock import AsyncMock
    app.state.organization.start=AsyncMock()
    service.csrf_token=app.state.ai_settings.csrf_token
    app.state.organization=service
    headers={'Host':'127.0.0.1','Origin':'http://127.0.0.1','X-Configuration-Token':service.csrf_token}
    with TestClient(app,base_url='http://127.0.0.1') as client:
        path='/api/v1/collection-organization/quality/'+identifier
        assert client.post(path+'/generate',json={'expected_version':1}).status_code==403
        assert client.post(path+'/generate',headers=headers,json={'expected_version':1}).status_code==200
        job=service._next();asyncio.run(service.run_job(job))
        view=client.get(path).json();assert view['candidate']
        assert client.post(path+'/adopt',headers=headers,json={'expected_version':1,'candidate_id':view['candidate']['id']}).status_code==200
        assert client.post('/api/v1/collection-organization/topics/config',headers=headers,json={'enabled':True}).status_code==200
        view=client.get('/api/v1/collection-organization/topics?topic=技术').json()
        assert view['enabled'] and view['member_count']==1
        assert client.post('/api/v1/collection-organization/topics/generate',headers=headers,
            json={'topic':'技术','expected_fingerprint':'0'*64}).status_code==409


def test_automation_can_resume_after_cancelled_extension(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    service.store.pause()
    assert service.store.read()['paused']
    assert not service.store.resume(None)['paused']
