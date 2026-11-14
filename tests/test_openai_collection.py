"""OpenAI wire contracts, exact counting, controlled transitions and accounting."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
import httpx
from pydantic import SecretStr
import pytest
from sqlalchemy import select,text
from alembic import command
from app.agents.configuration import AIProfile,ResolvedProfile
from app.agents.errors import AIError
from app.agents.transport import ModelClient
from app.models import OrganizationCall,OrganizationItem,Knowledge
from app.repositories.database import Database
from app.repositories.migrations import migration_config,upgrade_database
from app.services.organization.contracts import ProfileSwitch,OrganizationError,OrganizationWrite
from app.services.organization.providers import cost,price_snapshot
from test_collection_organization import organization,approved,article,run,PNG
from fastapi.testclient import TestClient
from app.main import create_app


def install_openai(service,model):
    old=service.calls.registry.resolve('deepseek')
    profile=AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol',
                      response_format='json_object',api_key_ref='openai')
    profiles={'deepseek':old.profile,'openai-responses':profile}
    def resolve(identifier):
        if identifier not in profiles:raise AIError(422,'ai_profile_unknown')
        return ResolvedProfile(identifier,profiles[identifier],SecretStr('synthetic-secret'),'synthetic')
    service.calls.registry=SimpleNamespace(resolve=resolve,profiles=profiles)
    counted=[]
    async def count(*args,**kwargs):counted.append(kwargs);return 100
    model.count_input_tokens=count
    return profiles,counted


def switch(service,**changes):
    state=service.store.read()
    target=service.calls.resolve({**state['config'],'profile_id':'openai-responses'})
    return service.store.switch_profile(ProfileSwitch(profile_id='openai-responses',
        **{'expected_revision':state['revision'],'expected_profile_fingerprint':target.fingerprint,**changes}))


def test_responses_images_and_count_use_identical_input_without_storage():
    profile=AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol',response_format='json_object')
    resolved=ResolvedProfile('openai',profile,SecretStr('synthetic-secret'),'synthetic')
    bodies=[]
    def handler(request):
        body=json.loads(request.content);bodies.append(body)
        assert request.headers['authorization']=='Bearer synthetic-secret'
        if request.url.path.endswith('/input_tokens'):
            return httpx.Response(200,json={'object':'response.input_tokens','input_tokens':1234})
        assert body['store'] is False and body['stream'] is False
        assert body['text']=={'format':{'type':'json_object'}}
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','role':'assistant',
            'content':[{'type':'output_text','text':'{"ok":true}'}]}],'usage':{'input_tokens':1234,'output_tokens':321}})
    async def exercise():
        client=ModelClient(httpx.MockTransport(handler));images=['data:image/png;base64,AAAA']
        assert await client.count_input_tokens(resolved,'JSON instructions','question',images=images)==1234
        reply=await client.generate(resolved,'JSON instructions','question',images=images)
        assert reply.usage['output_tokens']==321
    asyncio.run(exercise())
    assert all(bodies[0][key]==bodies[1][key] for key in ('model','input'))
    assert bodies[1]['input'][0]=={'role':'developer','content':'JSON instructions'}
    assert bodies[1]['input'][1]['content'][1]['type']=='input_image'


@pytest.mark.parametrize('bad',[True,-1,'123',None,2_000_001])
def test_invalid_counts_are_rejected_without_retry(bad):
    calls=[]
    def handler(request):calls.append(request);return httpx.Response(200,json={'object':'response.input_tokens','input_tokens':bad})
    resolved=ResolvedProfile('openai',AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol'),None,'test')
    with pytest.raises(AIError,match='invalid_token_count'):
        asyncio.run(ModelClient(httpx.MockTransport(handler)).count_input_tokens(resolved,'s','u'))
    assert len(calls)==1


def test_switch_preserves_published_files_fees_and_runs_only_new_articles(organization):
    service,model,source,output=organization
    approved(service,source);run(service,'all')
    before={str(p):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    with service.store.transaction() as session:
        original=[(r.id,r.accounted_micros) for r in session.scalars(select(OrganizationCall))]
    _,counted=install_openai(service,model)
    state=switch(service)
    assert state['approved'] and state['initial_complete'] and state['counts']=={'published':1}
    assert len(model.calls)==2 and not counted
    assert before=={str(p):p.read_bytes() for p in output.rglob('*') if p.is_file()}
    article(source,2);service.store.scan();assert run(service,'all')['status']=='completed'
    with service.store.transaction() as session:
        assert all(session.get(OrganizationCall,key).accounted_micros==value for key,value in original)
        newest=list(session.scalars(select(OrganizationCall)))[-1]
        assert newest.price_snapshot['provider']=='openai' and newest.accounted_micros==10000
        assert session.query(Knowledge).count()==2
    assert len(counted)==1 and len(model.calls)==3
    assert 'synthetic-secret' not in json.dumps(service.describe())
    service.store.scan()
    with pytest.raises(OrganizationError,match='no_pending_articles'):service.store.start('all')


@pytest.mark.parametrize('field',['expected_revision','expected_profile_fingerprint'])
def test_switch_rejects_stale_state_without_changing_approval(organization,field):
    service,model,source,_=organization
    approved(service,source);install_openai(service,model);before=service.store.read()
    with pytest.raises(OrganizationError):switch(service,**{field:'0'*64})
    assert service.store.read()==before


def test_switch_cannot_carry_changed_taxonomy_or_active_tasks(organization):
    service,model,source,_=organization
    approved(service,source);install_openai(service,model)
    service.store.start('all')
    with pytest.raises(OrganizationError,match='organization_busy'):switch(service)
    service.store.pause();job=service.store.read()['jobs'][0];service.store.cancel(job['id'])
    state=service.store.read();config={**state['config'],'taxonomy':state['config']['taxonomy']+['其他/新分类']}
    service.store.save(OrganizationWrite(**config,expected_revision=state['revision']))
    with pytest.raises(OrganizationError,match='sample_approval_required'):switch(service)


def test_same_id_model_edit_invalidates_approval_until_explicit_switch(organization):
    service,model,source,_=organization
    approved(service,source);run(service,'all');profiles,_=install_openai(service,model);switch(service)
    profiles['openai-responses']=profiles['openai-responses'].model_copy(update={'extra_body':{'text':{'verbosity':'low'}}})
    assert not service.store.read()['approved']
    with pytest.raises(OrganizationError,match='sample_approval_required'):service.store.start('all')
    assert switch(service)['approved']


def test_unpriced_openai_cache_options_are_rejected_before_http(organization):
    service,model,_,_=organization
    profiles,_=install_openai(service,model)
    profiles['openai-responses']=profiles['openai-responses'].model_copy(update={'extra_body':{'prompt_cache_options':{'ttl':'12h'}}})
    with pytest.raises(OrganizationError,match='organization_profile_unsupported'):
        service.calls.resolve({'profile_id':'openai-responses'})


@pytest.mark.parametrize('failure',['count','budget','generation'])
def test_count_failure_budget_and_timeout_never_retry_or_lose_reserves(organization,failure):
    service,model,source,_=organization
    approved(service,source);run(service,'all');install_openai(service,model);switch(service)
    state=service.store.read()
    service.store.save(OrganizationWrite(**{**state['config'],'monthly_budget_yuan':1},expected_revision=state['revision']))
    async def counted(*args,**kwargs):
        if failure=='count':raise AIError(502,'ai_upstream_error')
        return 50000 if failure=='budget' else 100
    model.count_input_tokens=counted;model.fail=failure=='generation'
    article(source,2);service.store.scan();job=run(service,'all')
    with service.store.transaction() as session:
        calls=list(session.scalars(select(OrganizationCall).where(OrganizationCall.price_snapshot['provider'].as_string()=='openai')))
        if failure=='generation':
            assert len(calls)==1 and calls[0].status=='uncertain'
            assert calls[0].accounted_micros==calls[0].reserved_micros>0
        else:assert not calls
    if failure=='budget':assert job['status']=='paused'
    assert len(model.calls)==(3 if failure=='generation' else 2)


def test_price_long_context_accounts_output_reasoning_and_legacy_rate():
    openai={'input_micros':20,'output_micros':80,'long_input_threshold':272000,'long_input_multiplier':2,'long_output_multiplier':1.5}
    assert cost(openai,100,100)==10000
    assert cost(openai,272001,100)==272001*40+12000
    assert cost({'input_micros':2,'output_micros':8},100,100)==1000


def test_price_migration_retains_historical_calls(sqlite_url):
    db=Database(sqlite_url);db.initialize()
    try:
        with db.engine.begin() as connection:
            config=migration_config();config.attributes['connection']=connection;command.upgrade(config,'0007')
            connection.execute(text("INSERT INTO organization_jobs(id,mode,status,selection,settings,created_at) VALUES('j','all','completed','[]','{}','time')"))
            connection.execute(text("INSERT INTO organization_calls(id,fingerprint,attempt,job_id,stage,period,status,reserved_micros,accounted_micros,created_at) VALUES('c','f',1,'j','summary','initial','uncertain',123,456,'time')"))
    finally:db.dispose()
    upgrade_database(sqlite_url);db.initialize()
    try:
        with db.engine.connect() as connection:
            assert tuple(connection.execute(text("SELECT reserved_micros,accounted_micros,price_snapshot FROM organization_calls WHERE id='c'")).one())==(123,456,None)
    finally:db.dispose()


def test_switch_api_requires_same_origin_and_write_token(organization,settings):
    original,model,source,_=organization
    approved(original,source);run(original,'all')
    with TestClient(create_app(settings),base_url='http://127.0.0.1:18000') as client:
        service=client.app.state.organization;service.calls.registry=original.calls.registry;install_openai(service,model)
        state=client.get('/api/v1/collection-organization').json()
        profile=next(x for x in state['available_profiles'] if x['id']=='openai-responses')
        payload={'profile_id':profile['id'],'expected_revision':state['revision'],'expected_profile_fingerprint':profile['fingerprint']}
        path='/api/v1/collection-organization/switch-profile'
        assert client.post(path,json=payload).status_code==403
        headers={'Origin':'http://127.0.0.1:18000','X-Configuration-Token':state['csrf_token']}
        assert client.post(path,json=payload,headers={**headers,'Origin':'https://foreign.example'}).status_code==403
        response=client.post(path,json=payload,headers=headers)
        assert response.status_code==200 and response.json()['approved']
