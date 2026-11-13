"""Collection state machine, paid-call recovery, export integrity and search."""
import asyncio
import hashlib
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.agents.configuration import AIProfile, ResolvedProfile
from app.agents.generation_gate import GenerationGate
from app.agents.protocols import ModelReply
from app.main import create_app
from app.models import OrganizationItem, OrganizationJob, OrganizationCall, Knowledge, Source
from app.repositories.database import Database
from app.services.content import ContentService
from app.services.organization.contracts import OrganizationError, OrganizationWrite
from app.services.organization.inventory import inspect_directory, chunks, sample_items
from app.services.organization.service import OrganizationService
from app.services.organization.search import keyword_search, semantic_search
from app.services.organization.publication import component

CATEGORIES = ['技术/人工智能','生活/经验','学习/方法','工作/职业','健康/常识','历史/文化','经济/观察','待分类/待确认']
PNG = b'\x89PNG\r\n\x1a\n' + b'synthetic image'


def article(root, number, body=None):
    root.mkdir(parents=True, exist_ok=True)
    path = root/f'{number}.md'
    content = body if body is not None else f'原文依据{number}。\n'+('人工智能与深度学习。方法需要实践检验。\n'*20)
    path.write_text(f'---\nid: "{number}"\ntitle: 测试文章{number}\nauthor: 作者\ntype: zhihu-article\nsource: https://zhuanlan.zhihu.com/p/{number}\n---\n'+content, encoding='utf-8')
    return path


class Model:
    def __init__(self):
        self.calls=[]
        self.fail=False

    async def generate(self, resolved, system, user, **kwargs):
        data=json.loads(user); self.calls.append((data, kwargs))
        if self.fail:
            raise TimeoutError()
        if 'titles' in data:
            output={'categories':CATEGORIES}
        elif 'images' in data:
            output={'observations':[{'image':i+1,'text':'图片呈现了人工智能的概念图。','uncertain':False} for i in range(len(data['images']))]}
        elif 'start' in data:
            output={'summary':'概括完整段落。','quotes':[data['content'][:20]]}
        else:
            quotes=[] if data['image_observations'] else ([data['content'][:20]] if data['content'] else data['parts'][0]['quotes'])
            output={'title':'从实践理解人工智能'+data['title'],'summary':'文章探讨人工智能和深度学习，强调通过实践检验方法。',
                    'category':CATEGORIES[0],'tags':['人工智能','学习','实践'],'points':['重视实践检验。','理解方法的适用边界。','结合原文证据。'],
                    'conditions':'仅为作者观点，需要结合实际情况判断。','quotes':quotes}
        return ModelReply(json.dumps(output,ensure_ascii=False),{'input_tokens':100,'output_tokens':100})


@pytest.fixture
def organization(settings, tmp_path):
    database=Database(settings.database_url); database.initialize()
    model=Model()
    profile=AIProfile(protocol='openai_chat',base_url='https://api.deepseek.com',model='deepseek-flash')
    registry=SimpleNamespace(resolve=lambda _:ResolvedProfile('deepseek',profile,None,'synthetic'))
    service=OrganizationService(database,RLock(),settings,registry,model,GenerationGate(),'synthetic')
    config={**service.store.read()['config'],'input_dir':str(tmp_path/'articles'),'output_dir':str(tmp_path/'organized')}
    service.store.save(OrganizationWrite(**config,expected_revision=service.store.read()['revision']))
    yield service, model, tmp_path/'articles', tmp_path/'organized'
    database.dispose()


def run(service,mode):
    job=service.store.start(mode)
    assert service._next()==job['id']
    asyncio.run(service.run_job(job['id']))
    return next(x for x in service.store.read()['jobs'] if x['id']==job['id'])


def approved(service, source, count=1):
    for n in range(1,count+1):article(source,n)
    service.store.scan()
    job=run(service,'sample')
    assert job['status']=='completed'
    service.store.approve(job['id'])
    return job


def test_full_workflow_preserves_originals_and_skips_model_on_publish(organization):
    service,model,source,output=organization
    for n in range(1,13):article(source,n)
    before={p.name:p.read_bytes() for p in source.glob('*.md')}
    service.store.scan()
    with pytest.raises(OrganizationError,match='sample_approval_required'):service.store.start('all')
    job=run(service,'sample')
    assert job['status']=='completed' and len(job['selection'])==10
    assert not output.exists()
    with service.store.transaction() as session:assert session.scalar(select(func.count()).select_from(Knowledge))==0
    service.store.approve(job['id'])
    assert run(service,'all')['status']=='completed'
    assert len(model.calls)==13 # one taxonomy plus twelve summaries
    assert len(list(output.glob('*/*/*.md')))==12
    assert service.store.read()['initial_complete']
    service.store.scan()
    with pytest.raises(OrganizationError,match='no_pending_articles'):service.store.start('all')
    assert before=={p.name:p.read_bytes() for p in source.glob('*.md')}
    with service.store.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Knowledge))==12
        assert session.scalar(select(func.count()).select_from(Source))==12
    assert keyword_search(service.store,'人工智能')['total']==12
    assert keyword_search(service.store,'实践')['total']==12
    assert keyword_search(service.store,'原文依据11')['total']==1
    assert keyword_search(service.store,'',category='无/结果')['total']==0


def test_sample_covers_two_visual_two_long_and_six_ordinary(organization):
    service,model,root,output=organization
    (root/'images').mkdir(parents=True)
    (root/'images/p.png').write_bytes(PNG)
    for n in range(1,7):article(root,n)
    for n in range(7,9):article(root,n,('完整的长文段落，需要保留结尾内容。\n'*1500)+f'末尾关键证据{n}')
    for n in range(9,11):article(root,n,'![图](images/p.png)')
    service.store.scan();job=run(service,'sample')
    assert job['status']=='completed'
    assert len(job['selection'])==10
    assert sum(bool(kwargs.get('images')) for _,kwargs in model.calls)==2
    segments=[x for x,_ in model.calls if 'start' in x]
    assert any('末尾关键证据7' in x['content'] for x in segments)
    service.store.approve(job['id']);assert run(service,'all')['status']=='completed'
    assert len(list((output/'assets').glob('*.png')))==1
    assert '../../assets/' in next(p.read_text(encoding='utf-8') for p in output.glob('*/*/*.md') if '![图]' in p.read_text(encoding='utf-8'))


def test_chunks_have_complete_coverage_and_overlap():
    body=('段落\n'*20000)+'末尾'
    parts=list(chunks(body))
    assert parts[0]['start']==0 and parts[-1]['end']==len(body)
    assert all(x['content']==body[x['start']:x['end']] and len(x['content'])<=12000 for x in parts)
    assert all(b['start']==a['end']-200 for a,b in zip(parts,parts[1:]))


def test_timeout_is_not_retried_until_explicit_sample_retry(organization):
    service,model,source,_=organization
    article(source,1);service.store.scan();model.fail=True
    job=run(service,'sample');assert job['status']=='failed'
    assert len(model.calls)==1
    service.store.recover()
    # Starting another sample does not silently repeat the uncertain taxonomy call.
    job=run(service,'sample');assert job['status']=='failed' and len(model.calls)==1
    model.fail=False
    service.store.retry_sample(job['id']);assert service._next()==job['id']
    asyncio.run(service.run_job(job['id']))
    assert service.store.read()['counts']['ready']==1 and len(model.calls)==3
    with service.store.transaction() as session:
        calls=list(session.scalars(select(OrganizationCall)))
        assert calls[0].accounted_micros==calls[0].reserved_micros


def test_budget_is_reserved_before_http_and_resume_reuses_response(organization):
    service,model,source,_=organization
    approved(service,source)
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem))
        item.result=None;item.status='discovered'
        call=session.scalar(select(OrganizationCall).where(OrganizationCall.stage=='summary'))
        call.response=None;call.status='uncertain';call.accounted_micros=20_000_000
        item.status='failed'
    job=run(service,'retry')
    assert job['status']=='paused' and job['error']=='organization_budget_exhausted'
    assert len(model.calls)==2
    state=service.store.read();config={**state['config'],'initial_budget_yuan':21}
    service.store.save(OrganizationWrite(**config,expected_revision=state['revision']))
    assert service.store.read()['approved']
    service.store.resume(job['id']);assert service._next()==job['id']
    asyncio.run(service.run_job(job['id']))
    assert service.store.read()['counts']['published']==1 and len(model.calls)==3


def test_interrupted_paid_reservation_never_becomes_free(organization):
    service,_,source,_=organization
    article(source,1);service.store.scan();job=service.store.start('sample');service._next()
    with service.store.transaction() as session:
        session.add(OrganizationCall(fingerprint='a'*64,attempt=1,job_id=job['id'],stage='taxonomy',period='initial',
                                     reserved_micros=50000,accounted_micros=50000))
    service.store.recover()
    with service.store.transaction() as session:
        call=session.scalar(select(OrganizationCall))
        assert call.status=='uncertain' and call.accounted_micros==50000
        assert session.get(OrganizationJob,job['id']).status=='pending'


def test_pause_persists_and_result_from_inflight_call_is_saved(organization):
    service,model,source,output=organization
    article(source,1);service.store.scan()
    base=model.generate
    async def delayed(*args,**kwargs):
        reply=await base(*args,**kwargs)
        if 'content' in json.loads(args[2]):service.store.pause()
        return reply
    model.generate=delayed
    job=run(service,'sample')
    assert job['status']=='paused' and service.store.read()['counts']['ready']==1
    service.store.recover();assert service._next() is None
    model.generate=base;service.store.resume(job['id']);service._next()
    asyncio.run(service.run_job(job['id']))
    assert len(model.calls)==2 and not output.exists()


def test_export_rename_and_external_edit_never_regenerate(organization):
    service,model,source,output=organization
    approved(service,source);run(service,'all')
    record=service.store.items()['items'][0];old=output/record['export_path']
    with service.store.transaction() as session:
        note=session.get(Knowledge,record['knowledge_id'])
        ContentService(session).update_knowledge(note.id,note.version,{'title':'修改后的新标题','category':'生活/经验'})
    assert keyword_search(service.store,'')['total']==0 # never return stale FTS
    service.publication.refresh(service.store.read()['config'])
    record=service.store.items()['items'][0];new=output/record['export_path']
    assert not old.exists() and new.exists()
    new.write_text('外部编辑保留',encoding='utf-8')
    with service.store.transaction() as session:
        note=session.get(Knowledge,record['knowledge_id'])
        ContentService(session).update_knowledge(note.id,note.version,{'title':'再次修改'})
    service.publication.refresh(service.store.read()['config'])
    assert service.store.items()['items'][0]['error']=='export_conflict'
    assert new.read_text(encoding='utf-8')=='外部编辑保留' and len(model.calls)==2


def test_source_change_is_detected_and_images_are_fingerprinted(organization):
    service,_,source,_=organization
    (source/'images').mkdir(parents=True);(source/'images/p.png').write_bytes(PNG)
    article(source,1,'![图](images/p.png)');service.store.scan()
    before=inspect_directory(source)[0]['input_hash']
    (source/'images/p.png').write_bytes(PNG+b'changed')
    assert inspect_directory(source)[0]['input_hash']!=before
    service.store.scan();assert service.store.items()['items'][0]['error']=='source_changed'
    with pytest.raises(OrganizationError,match='no_pending_articles'):service.store.start('sample')


def test_semantic_filter_precedes_candidate_retrieval(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    expected=service.store.items()['items'][0]['knowledge_id']
    class Retrieval:
        async def retrieve(self,q,n,*,knowledge_ids):
            assert knowledge_ids=={expected}
            return {'notes':[{'knowledge_id':expected}],'index_incomplete':False}
    result=asyncio.run(semantic_search(service.store,Retrieval(),'如何实践',CATEGORIES[0],'实践'))
    assert result['total']==1


@pytest.mark.parametrize('name',['CON','NUL','COM1','LPT2.txt','..','a/b:*?'])
def test_filename_components_are_windows_safe(name):
    from pathlib import PureWindowsPath
    assert not PureWindowsPath(component(name)).is_reserved()
    assert component(name) not in {'.','..',''} and '/' not in component(name)


def test_api_guards_and_disabled_startup_make_no_paid_calls(settings,tmp_path):
    model=Model()
    with TestClient(create_app(settings,model_client=model),base_url='http://127.0.0.1:18000') as client:
        endpoint='/api/v1/collection-organization'
        result=client.get(endpoint);state=result.json()
        assert result.status_code==200 and result.headers['cache-control']=='no-store'
        config={**state['config'],'input_dir':str(tmp_path/'articles'),'output_dir':str(tmp_path/'organized'),'expected_revision':state['revision']}
        assert client.put(endpoint,json=config).status_code==403
        headers={'Origin':'http://127.0.0.1:18000','X-Configuration-Token':state['csrf_token']}
        assert client.put(endpoint,json=config,headers=headers).status_code==200
        assert client.put(endpoint,json=config,headers=headers).status_code==409
        assert client.post(endpoint+'/sample',json={}).status_code==403
        assert client.get(endpoint,headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.get(endpoint+'/search?q=人工').json()['total']==0
        assert client.get(endpoint+'/assets/not-safe.png').status_code==404
    assert not model.calls


def test_new_article_uses_monthly_budget_and_leaves_successful_items_alone(organization):
    service,model,source,_=organization
    approved(service,source);run(service,'all')
    article(source,2);service.store.scan()
    assert run(service,'auto')['status']=='completed'
    assert len(model.calls)==3
    with service.store.transaction() as session:
        call=session.scalars(select(OrganizationCall).order_by(OrganizationCall.created_at.desc())).first()
        assert call.period!='initial' and len(call.period)==7
        assert session.scalar(select(func.count()).select_from(Knowledge))==2


def test_export_retry_reuses_saved_summary_and_existing_knowledge(organization):
    service,model,source,output=organization
    approved(service,source);run(service,'all')
    row=service.store.items()['items'][0];path=output/row['export_path']
    original=path.read_bytes();path.write_bytes(b'edited')
    service.publication.refresh(service.store.read()['config'])
    assert service.store.read()['counts']['failed']==1
    path.write_bytes(original)
    assert run(service,'retry')['status']=='completed'
    assert len(model.calls)==2
    with service.store.transaction() as session:assert session.scalar(select(func.count()).select_from(Knowledge))==1


def test_unfaithful_quote_fails_without_publication(organization):
    service,model,source,_=organization
    article(source,1);service.store.scan();base=model.generate
    async def invalid(*args,**kwargs):
        reply=await base(*args,**kwargs);data=json.loads(reply.text)
        if 'quotes' in data:data['quotes']=['编造并不在原文中的逐字引用']
        return ModelReply(json.dumps(data),reply.usage)
    model.generate=invalid
    job=run(service,'sample')
    assert job['status']=='completed_with_errors'
    assert service.store.items()['items'][0]['error']=='organization_output_invalid'
    with pytest.raises(OrganizationError,match='sample_not_ready'):service.store.approve(job['id'])
    assert len(model.calls)==2


def test_cached_received_response_can_be_revalidated_without_http(organization):
    service,model,source,_=organization
    job=approved(service,source)
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem));item.result=None;item.status='discovered'
        call=session.scalar(select(OrganizationCall).where(OrganizationCall.stage=='summary'));call.status='received'
    assert run(service,'all')['status']=='completed' and len(model.calls)==2


@pytest.mark.parametrize('q',['%','_','!','"','" OR *','不存在'])
def test_keyword_literals_never_become_patterns_or_fts_operators(organization,q):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    assert keyword_search(service.store,q)['total']==0


def test_deleted_notes_are_not_searchable(organization):
    service,_,source,_=organization
    approved(service,source);run(service,'all')
    with service.store.transaction() as session:
        note=session.scalar(select(Knowledge));note.deleted_at='2026-01-01'
    assert keyword_search(service.store,'人工智能')['total']==0


def test_read_only_instance_refuses_jobs_and_does_not_recover(settings):
    settings=settings.model_copy(update={'configuration_read_only':True})
    with TestClient(create_app(settings),base_url='http://127.0.0.1:18000') as client:
        state=client.get('/api/v1/collection-organization').json()
        headers={'Origin':'http://127.0.0.1:18000','X-Configuration-Token':state['csrf_token']}
        assert client.post('/api/v1/collection-organization/sample',json={},headers=headers).status_code==409
        assert client.app.state.organization.task is None


def test_cancel_paused_task_keeps_paid_results_and_allows_new_sample(organization):
    service,model,source,_=organization
    approved(service,source)
    job=service.store.start('all');service.store.pause()
    service.store.cancel(job['id'])
    assert service.store.read()['paused']
    assert run(service,'sample')['status']=='completed'
    assert len(model.calls)==2


def test_inline_images_use_chat_blocks_without_changing_text_requests():
    import httpx
    from app.agents.transport import ModelClient
    bodies=[]
    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                                       'usage':{'prompt_tokens':1,'completion_tokens':1}})
    profile=AIProfile(protocol='openai_chat',base_url='https://api.deepseek.com',model='deepseek-flash')
    resolved=ResolvedProfile('deepseek',profile,None,'synthetic')
    client=ModelClient(httpx.MockTransport(handler))
    asyncio.run(client.generate(resolved,'system','user',images=['data:image/png;base64,c3ludGhldGlj']))
    asyncio.run(client.generate(resolved,'system','user'))
    assert bodies[0]['messages'][1]['content'][1]['image_url']['detail']=='original'
    assert bodies[1]['messages'][1]['content']=='user'


def test_only_literal_grounded_quotes_survive_normalization():
    from app.services.organization.generation import grounded_quotes,summary_validator
    assert grounded_quotes(['甲','编造','乙','丙','丁','甲'],'甲乙丙丁')==['甲','乙','丙']
    assert grounded_quotes(['图片OCR文字'],'![图](p.png)',required=False)==[]
    with pytest.raises(ValueError):grounded_quotes(['编造'],'原文')


def test_revalidate_saved_invalid_response_without_repeat_paid_request(organization):
    service,model,source,_=organization
    article(source,1);service.store.scan()
    job=run(service,'sample')
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem));item.result=None;item.status='failed';item.error='organization_output_invalid'
        call=session.scalar(select(OrganizationCall).where(OrganizationCall.stage=='summary'))
        value=json.loads(call.response);value['quotes'] += ['不在原文中的内容'];call.response=json.dumps(value);call.status='invalid'
        session.get(OrganizationJob,job['id']).status='completed_with_errors'
    service.store.retry_sample(job['id'],False);service._next();asyncio.run(service.run_job(job['id']))
    assert service.store.items()['items'][0]['status']=='ready' and len(model.calls)==2
    assert len(service.store.items()['items'][0]['result']['quotes'])==1


def test_invalid_cache_continuation_never_repeats_failed_http(organization):
    service,model,source,_=organization
    article(source,1);service.store.scan();model.fail=True
    job=run(service,'sample')
    service.store.retry_sample(job['id'],False);service._next();asyncio.run(service.run_job(job['id']))
    assert len(model.calls)==1
    assert service.store.read()['jobs'][0]['error']=='explicit_retry_required'


def test_bounded_verbose_chunk_keeps_full_summary_and_three_literal_quotes(organization):
    service,model,source,_=organization
    article(source,1,'甲乙丙丁戊'*5000);service.store.scan();base=model.generate
    async def verbose(*args,**kwargs):
        reply=await base(*args,**kwargs)
        if 'start' in json.loads(args[2]):
            return ModelReply(json.dumps({'summary':'有依据的段落概括。'*100,'quotes':list('甲乙丙丁戊')}),reply.usage)
        return reply
    model.generate=verbose
    assert run(service,'sample')['status']=='completed'
    assert all(len(x['quotes'])==3 for data,_ in model.calls if 'parts' in data for x in data['parts'])


def test_formatting_only_quote_resolution_returns_exact_original_slice():
    from app.services.organization.generation import grounded_quotes
    body='第一段。\n\n只看**作者观点**，需要\n\n证据支持。请读[原文](https://example.test)再判断。'
    quotes=grounded_quotes(['只看作者观点，需要证据支持。','请读原文再判断。'],body)
    assert quotes==['只看**作者观点**，需要\n\n证据支持。','请读[原文](https://example.test)再判断。']
    assert all(q in body for q in quotes)
    with pytest.raises(ValueError):grounded_quotes(['只看权威事实，需要证据支持。'],body)
    with pytest.raises(ValueError):grounded_quotes(['不爱'], '不，爱')


def test_cached_failed_items_can_continue_without_new_request(organization):
    service,model,source,_=organization
    approved(service,source)
    with service.store.transaction() as session:
        item=session.scalar(select(OrganizationItem));item.status='failed';item.result=None;item.error='organization_output_invalid'
        call=session.scalar(select(OrganizationCall).where(OrganizationCall.stage=='summary'));call.status='invalid'
    assert run(service,'continue')['status']=='completed'
    assert len(model.calls)==2


def test_long_quote_is_only_shortened_after_full_source_match():
    from app.services.organization.generation import grounded_quotes
    body='证据完整。'+'条件需要保留'*40+'。'
    assert grounded_quotes([body],body)==['证据完整。']
    with pytest.raises(ValueError):grounded_quotes([body+'编造结论。'],body)
    with pytest.raises(ValueError):grounded_quotes(['字'*201],'字'*201)
