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
