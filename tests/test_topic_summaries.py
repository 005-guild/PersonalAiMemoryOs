"""Multi-group evidence, cache reuse, membership invalidation and optional reads."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.models import Knowledge, OrganizationJob, TopicSummary
from app.services.content import ContentService
from app.services.topics.service import TopicService
from app.services.topics.contracts import validate
from app.services.organization.contracts import OrganizationError
from test_collection_organization import organization, approved, run


def result(reference):
    return {'overview':'文章讨论实践学习。','points':[{'heading':'实践','text':'作者强调实践检验。','references':[reference]}],
            'disagreements':[],'conditions':'来自单篇摘要及原文片段，适用范围有限。'}


def test_topic_groups_cache_and_stale_members(organization):
    service,_,source,_=organization
    approved(service,source,25);run(service,'all')
    topics=TopicService(service);topics.toggle(True)
    calls=[]
    async def generate(resolved,system,user,**kwargs):
        data=json.loads(user);calls.append(data)
        if 'articles' in data:
            article=data['articles'][0];evidence=article['evidence'][0]
            reference={'knowledge_id':article['knowledge_id'],'evidence_id':evidence['id'],'quote':evidence['text']}
        else:reference=data['group_summaries'][0]['points'][0]['references'][0]
        return SimpleNamespace(text=json.dumps(result(reference)),usage={'input_tokens':100,'output_tokens':100})
    service.calls.client=SimpleNamespace(generate=generate)
    view=topics.view('技术');assert view['member_count']==25 and not view['result']
    job=topics.start('技术',view['fingerprint']);service._next();asyncio.run(service.run_job(job['id']))
    view=topics.view('技术');assert view['result'] and not view['stale'] and not view['pending']
    assert len(calls)==4
    assert sum(len(row['articles']) for row in calls if 'articles' in row)==25
    job=topics.start('技术',view['fingerprint']);service._next();asyncio.run(service.run_job(job['id']))
    assert len(calls)==4
    with service.store.transaction() as session:
        note=session.scalar(select(Knowledge));ContentService(session).update_knowledge(note.id,note.version,{'summary':'人工修订的新摘要'})
    service.publication.refresh(service.store.read()['config'])
    assert topics.view('技术')['stale']
    with pytest.raises(OrganizationError):topics.start('技术',view['fingerprint'])
    topics.toggle(False)
    assert not topics.view('技术')['enabled']
    with pytest.raises(OrganizationError):topics.start('技术',topics.view('技术')['fingerprint'])


def test_topic_references_require_literal_grounded_evidence():
    articles=[{'knowledge_id':'one','evidence':[{'id':'Q1','text':'连续的原文依据'}]}]
    reference={'knowledge_id':'one','evidence_id':'Q1','quote':'原文依据'}
    assert validate(result(reference),articles)
    for changed in [{'knowledge_id':'other'},{'quote':'虚构引文'},{'evidence_id':'O1'}]:
        with pytest.raises(ValueError):validate(result({**reference,**changed}),articles)


def test_recovery_pauses_extension_jobs_without_repeating_calls(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    with service.store.transaction() as session:
        job=OrganizationJob(mode='topic',status='running',selection=[],settings={})
        session.add(job);session.flush();identifier=job.id
    service.store.recover()
    with service.store.transaction() as session:
        assert session.get(OrganizationJob,identifier).status=='paused'
        assert service.store.control(session)['paused']
