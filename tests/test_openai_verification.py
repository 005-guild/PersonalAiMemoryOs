import asyncio,json
from types import SimpleNamespace
import httpx
import pytest
from app.agents.configuration import AIProfile,ResolvedProfile
from app.agents.errors import AIError
from app.agents.transport import ModelClient
from scripts import verify_openai_default as verification


def profile():
    return ResolvedProfile('openai',AIProfile(protocol='openai_responses',base_url='https://api.openai.com/v1',model='gpt-6.1-sol',max_output_tokens=2048),None,'synthetic')


def test_validation_intent_precedes_http_and_timeout_retains_money(tmp_path,monkeypatch):
    journal=tmp_path/'budget.json';monkeypatch.setattr(verification,'LEDGER',journal)
    class Client:
        async def count_input_tokens(self,*args,**kwargs):return 100
        async def generate(self,*args,**kwargs):
            assert json.loads(journal.read_text())['calls'][0]['status']=='reserved'
            raise AIError(504,'ai_timeout')
    ledger={'calls':[]};model=verification.BudgetClient(profile(),tmp_path,ledger,Client())
    with pytest.raises(RuntimeError,match='ai_timeout'):asyncio.run(model.generate(profile(),'system','input'))
    row=ledger['calls'][0]
    assert row['status']=='uncertain' and row['accounted_micros']==row['reserved_micros']>0


@pytest.mark.parametrize('reason',['money','calls'])
def test_validation_caps_do_not_issue_generation(tmp_path,monkeypatch,reason):
    monkeypatch.setattr(verification,'LEDGER',tmp_path/'budget.json')
    class Client:
        async def count_input_tokens(self,*args,**kwargs):return 100
        async def generate(self,*args,**kwargs):raise AssertionError('Budget exceeded')
    rows=[{'accounted_micros':2_000_000}] if reason=='money' else [{'accounted_micros':0}]*4
    model=verification.BudgetClient(profile(),tmp_path,{'calls':rows},Client())
    with pytest.raises(RuntimeError,match='validation_.*(exhausted|limit)'):
        asyncio.run(model.generate(profile(),'system','input'))


def test_http_diagnostics_discard_provider_messages_and_unknown_codes():
    def handler(request):
        return httpx.Response(400,json={'error':{'code':'private-key-in-code','message':'private-key-in-message','param':'input'}})
    with pytest.raises(AIError) as captured:
        asyncio.run(ModelClient(httpx.MockTransport(handler)).generate(profile(),'system','input'))
    error=captured.value
    assert error.provider_status==400 and error.provider_parameter=='input'
    assert not hasattr(error,'provider_code')
    assert 'private-key' not in str(error) and 'private-key' not in repr(error.__dict__)
