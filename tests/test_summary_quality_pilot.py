import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.agents.configuration import AIProfile,ResolvedProfile
from app.services.organization.contracts import fingerprint
from scripts.summary_quality.budget import Budget,budget_lock,CAP
from scripts.summary_quality.generation import validate,pilot_profile
from scripts.summary_quality.storage import save,load,freeze,verify_sources
from scripts.summary_quality.report import render
from test_collection_organization import organization


def profile():
    return ResolvedProfile('openai',AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol'),None,'test')


class Client:
    def __init__(self):self.calls=0
    async def count_input_tokens(self,*args):return 100
    async def generate(self,*args):
        self.calls+=1
        return SimpleNamespace(text='{}',usage={'input_tokens':100,'output_tokens':50})


def test_budget_survives_new_instance_and_reuses_received_reply(tmp_path):
    client=Client();budget=Budget(tmp_path,client,profile())
    text,row=asyncio.run(budget.generate('same','system','input'))
    assert row['accounted_micros']==6000
    assert asyncio.run(Budget(tmp_path,client,profile()).generate('same','system','input'))[0]==text
    assert client.calls==1
    ledger=load(tmp_path/'budget.json');ledger['calls'][0]['accounted_micros']=CAP
    save(tmp_path/'budget.json',ledger)
    with pytest.raises(RuntimeError,match='budget_exhausted'):
        asyncio.run(Budget(tmp_path,client,profile()).generate('other','system','input'))
    assert client.calls==1


def test_intent_precedes_generation_and_uncertainty_is_not_retried(tmp_path):
    class Failure(Client):
        async def generate(self,*args):
            assert load(tmp_path/'budget.json')['calls'][0]['status']=='reserved'
            self.calls+=1;raise TimeoutError()
    client=Failure();budget=Budget(tmp_path,client,profile())
    with pytest.raises(RuntimeError,match='model_call_failed'):asyncio.run(budget.generate('same','s','u'))
    row=load(tmp_path/'budget.json')['calls'][0]
    assert row['status']=='uncertain' and row['accounted_micros']==row['reserved_micros']
    with pytest.raises(RuntimeError,match='explicit_retry'):asyncio.run(Budget(tmp_path,client,profile()).generate('same','s','u'))
    assert client.calls==1


@pytest.mark.parametrize('reason',['count','capacity','counter_failure'])
def test_generation_never_occurs_when_limits_or_counting_fail(tmp_path,reason):
    class Limited(Client):
        async def count_input_tokens(self,*args):
            if reason=='counter_failure':raise RuntimeError('count_failed')
            return 272001 if reason=='capacity' else 100
    client=Limited();budget=Budget(tmp_path,client,profile())
    if reason=='count':
        budget.ledger['calls']=[{'fingerprint':str(i),'accounted_micros':0} for i in range(10)]
    with pytest.raises(RuntimeError):asyncio.run(budget.generate('new','s','u'))
    assert client.calls==0


def test_lock_and_default_model_are_explicit(tmp_path):
    with budget_lock(tmp_path):
        with pytest.raises(FileExistsError):
            with budget_lock(tmp_path):pass
    active=profile()
    selected=pilot_profile(SimpleNamespace(default_profile='openai',resolve=lambda _:active))
    assert selected.profile.max_output_tokens==4096 and selected.profile.extra_body['reasoning']=={'effort':'low'}
    assert not (tmp_path/'budget.lock').exists()


def sample(visual=False,partial=False):
    return {'original':{'content':'这是原文中的连续论据。'},'observations':[{'id':'O1','text':'清晰内容'}] if visual else [],
            'image_only':visual,'partial':partial}


def output(visual=False):
    return {'summary':'原文讨论一个问题。','overview':'作者描述自己的经历。',
        'points':[{'heading':'经历','detail':'保留原文的条件。','evidence_ids':['O1' if visual else 'Q1']}],
        'conditions':'这不是普遍规律。','conclusion':'作者未提出确定结论。',
        'source_quotes':[] if visual else [{'id':'Q1','quote':'这是原文中的连续论据。'}],
        'image_evidence_ids':['O1'] if visual else []}


def test_literal_and_image_evidence_cannot_be_invented_or_confused():
    assert validate(json.dumps(output()),sample())['source_quotes']
    for change in ['quote','point','image']:
        value=output()
        if change=='quote':value['source_quotes'][0]['quote']='编造引文'
        elif change=='point':value['points'][0]['evidence_ids']=['Q6']
        else:value['image_evidence_ids']=['O9']
        with pytest.raises(ValueError):validate(json.dumps(value),sample())
    assert validate(json.dumps(output(True)),sample(True))['image_evidence_ids']==['O1']
    caption=output(True);caption['source_quotes']=output()['source_quotes']
    assert validate(json.dumps(caption),sample(True))['source_quotes']
    caption['source_quotes'][0]['quote']='把图片识读当作原文'
    with pytest.raises(ValueError):validate(json.dumps(caption),sample(True))
    with pytest.raises(ValueError):validate(json.dumps(output(True)),sample(True,True))
    value=output(True)
    for field in ('summary','overview','conditions'):value[field]+='部分图片文字无法辨认。'
    assert validate(json.dumps(value),sample(True,True))


def test_offline_report_escapes_private_source_html_and_does_not_claim_review(tmp_path):
    value={'identity':'one','kind':'普通文章','current':{'title':'<script>alert(1)</script>','category':'主题','summary':'旧摘要','body':'旧正文'},
           'original':{'title':'原题','content':'<img src=https://example.com>'},'files':{},'observations':[]}
    packet={'samples':[value]};review={'articles':[{'identity':'one','outcome':'pending','scores':{}}]}
    status=render(packet,{'one':{'status':'succeeded','candidate':output()}},review,{'calls':[]},tmp_path)
    html=(tmp_path/'report.html').read_text(encoding='utf-8')
    assert '<script>' not in html and '<img src=https' not in html
    assert '&lt;script&gt;' in html and "default-src 'none'" in html
    assert not status['promotion_gate'] and status['reviewed']==0


def test_prepare_and_recheck_are_readonly_and_cover_the_required_samples(organization,tmp_path,monkeypatch):
    # Use the established synthetic collection fixture to publish ten articles.
    from test_collection_organization import article,run,PNG
    from app.models import OrganizationItem,Knowledge
    from sqlalchemy import select
    service,model,source,output_dir=organization
    source.mkdir();(source/'p.png').write_bytes(PNG)
    for n in range(1,11):article(source,n,('![图片](p.png)' if n<=2 else '这是完整可引用的原始文字。'*(1700 if n<=4 else 20)))
    service.store.scan();job=run(service,'sample');service.store.approve(job['id']);run(service,'all')
    with service.store.transaction() as session:
        items=list(session.scalars(select(OrganizationItem).order_by(OrganizationItem.identity)))
        # Mark one visual item partial; its observed clear records remain usable.
        items[0].result={**items[0].result,'partial_image_summary':True}
    database=service.store.database.url.database
    with service.store.database.session() as session:before='\n'.join(session.connection().connection.driver_connection.iterdump())
    destination=tmp_path/'packet';packet=freeze(database,destination)
    assert len(packet['samples'])==10
    assert [x['kind'] for x in packet['samples']].count('长文')==2
    assert packet['samples'][0]['partial']
    verify_sources(packet)
    from scripts import summary_quality_pilot as pilot
    monkeypatch.setattr(pilot,'BUDGET_ROOT',tmp_path/'shared-budget')
    class Grounded(Client):
        async def generate(self,resolved,system,user):
            self.calls+=1;data=json.loads(user);visual=bool(data['clear_image_observations'])
            value=__import__(__name__,fromlist=['output']).output(visual)
            if visual:
                value['image_evidence_ids']=[data['clear_image_observations'][0]['id']]
                value['points'][0]['evidence_ids']=value['image_evidence_ids']
            else:value['source_quotes'][0]['quote']=data['content'][:20]
            if data['partial_image_input']:
                for field in ('summary','overview','conditions'):value[field]+='部分图片文字无法辨认。'
            return SimpleNamespace(text=json.dumps(value),usage={'input_tokens':100,'output_tokens':100})
    fake=Grounded()
    assert asyncio.run(pilot.generate(destination,profile(),fake))['generated']==10
    other=tmp_path/'second-output';other.mkdir();save(other/'samples.json',packet)
    assert asyncio.run(pilot.generate(other,profile(),fake))['generated']==10
    assert fake.calls==10  # A new output directory cannot trigger repeat charges.
    with service.store.database.session() as session:assert '\n'.join(session.connection().connection.driver_connection.iterdump())==before
    path=Path(next(iter(packet['samples'][0]['files'])));path.write_text('changed',encoding='utf-8')
    with pytest.raises(RuntimeError,match='original_changed'):verify_sources(packet)
