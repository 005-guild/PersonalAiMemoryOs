"""Explicit budgeted OpenAI acceptance on synthetic inputs, without formal writes."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from app.agents.configuration import AIRegistry,ResolvedProfile
from app.agents.generation_gate import GenerationGate
from app.agents.transport import ModelClient,_unique_keys,_invalid_constant
from app.config import Settings
from app.services.organization.contracts import fingerprint
from app.services.organization.generation import summarize,prompt
from app.services.organization.inventory import inspect_directory
from app.services.organization.images import image_inputs,input_label
from app.services.organization.providers import resolve,price_snapshot,cost
from app.services.rag_answer import RagAnswerService

LEDGER=ROOT/'.cache/openai-validation-budget.json'


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


class BudgetClient:
    def __init__(self,resolved,evidence,ledger,client=None,*,reviewed_extra_qa=False):
        self.resolved,self.evidence,self.ledger=resolved,evidence,ledger
        self.client=client or ModelClient()
        self.prices=price_snapshot(resolved)
        self.max_calls=5 if reviewed_extra_qa else 4

    async def generate(self,resolved,system,user,*,images=None):
        if resolved.fingerprint!=self.resolved.fingerprint:raise RuntimeError('validation_profile_changed')
        if len(self.ledger['calls'])>=self.max_calls:raise RuntimeError('validation_call_limit')
        incoming=await self.client.count_input_tokens(resolved,system,user,images=images)
        reserve=cost(self.prices,incoming+256,resolved.profile.max_output_tokens)
        if sum(row['accounted_micros'] for row in self.ledger['calls'])+reserve>2_000_000:
            raise RuntimeError('validation_budget_exhausted')
        row={'number':len(self.ledger['calls'])+1,'status':'reserved','accounted_micros':reserve,
             'reserved_micros':reserve,'input_estimate':incoming,'model':resolved.profile.model,
             'profile_fingerprint':resolved.fingerprint,'system_hash':hashlib.sha256(system.encode()).hexdigest(),
             'user_hash':hashlib.sha256(user.encode()).hexdigest(),'price_snapshot':self.prices}
        self.ledger['calls'].append(row);save(LEDGER,self.ledger)
        try:
            reply=await self.client.generate(resolved,system,user,images=images)
        except Exception as error:
            row.update(status='uncertain',error=getattr(error,'code','model_call_failed'))
            for field in ('provider_status','provider_code','provider_parameter'):
                if hasattr(error,field):row[field]=getattr(error,field)
            save(LEDGER,self.ledger)
            raise RuntimeError(row['error']) from None
        row.update(status='returned',usage=reply.usage)
        incoming,outgoing=reply.usage.get('input_tokens'),reply.usage.get('output_tokens')
        if type(incoming) is int and type(outgoing) is int and incoming>=0 and outgoing>=0:
            row['accounted_micros']=cost(self.prices,incoming,outgoing)
        save(self.evidence/f"response-{row['number']}.json",{'text':reply.text,'usage':reply.usage})
        save(LEDGER,self.ledger)
        return reply


class ValidationCalls:
    def __init__(self,client,resolved):self.client,self.resolved=client,resolved

    async def generate(self,job_id,item_id,stage,system,user,validate,images=None,repair_system=None):
        reply=await self.client.generate(self.resolved,system,user,images=images)
        return validate(json.loads(reply.text,object_pairs_hook=_unique_keys,parse_constant=_invalid_constant))


async def exercise(resolved,evidence,ledger):
    source=evidence/'articles';source.mkdir()
    raw='备份成功不等于已经能够恢复。先核对备份的文件清单与哈希，再在隔离目录执行恢复。恢复后检查记录数量、关键关联和文件内容。只有恢复检查通过，才能确认这份备份可用。不要在正式目录直接进行恢复演练。'
    (source/'1.md').write_text('---\nid: "910000001"\ntitle: 验证备份是否可用\ntype: zhihu-article\nsource: https://zhuanlan.zhihu.com/p/910000001\n---\n'+raw*3,encoding='utf-8')
    images=source/'images';images.mkdir()
    image=Image.new('RGB',(1200,700),'white');draw=ImageDraw.Draw(image);font=ImageFont.load_default(size=38)
    for index,line in enumerate(['VERIFY BACKUPS BY RESTORING FILES','1. Check file hashes.','2. Restore into an isolated folder.','3. Compare records and file contents.','4. Keep the original data safe.']):
        draw.text((25,45+index*105),line,font=font,fill='black')
    image.save(images/'backup.png')
    (source/'2.md').write_text('---\nid: "910000002"\ntitle: 备份恢复检查图\ntype: zhihu-article\nsource: https://zhuanlan.zhihu.com/p/910000002\n---\n![恢复检查图](images/backup.png)',encoding='utf-8')
    snapshots=inspect_directory(source);originals={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    client=BudgetClient(resolved,evidence,ledger);calls=ValidationCalls(client,resolved)
    config={'input_dir':str(source),'taxonomy':['技术/备份与恢复','待分类/待确认']}
    result=await summarize(calls,'isolated-validation',snapshots[0]['identity'],snapshots[0],config)
    assert result['quotes'];save(evidence/'summaries.json',[result])
    batch=next(image_inputs(snapshots[1],source))
    def validate_vision(value):
        rows=value['observations']
        if type(value.get('uncertain')) is bool:rows=[{'uncertain':value['uncertain'],**row} for row in rows]
        assert len(rows)==len(batch)
        for number,row in enumerate(rows,1):
            assert set(row)=={'image','text','uncertain'} and row['image']==number
            assert type(row['uncertain']) is bool and not row['uncertain'] and 1<=len(row['text'])<=1500
        return rows
    vision=await calls.generate('isolated-validation',None,'vision',prompt('vision'),
        json.dumps({'title':snapshots[1]['values']['title'],'images':[input_label(x) for x in batch]},ensure_ascii=False),
        validate_vision,images=[x['data'] for x in batch])
    save(evidence/'vision.json',vision)
    class Search:
        async def search(self,query,limit):
            return {'items':[{'chunk_id':'synthetic-backup','title':'验证备份是否可用','text':raw}], 'index_incomplete':False}
        def validate_context(self,contexts):return contexts[0]['text']==raw
    answerer=RagAnswerService(Search(),SimpleNamespace(resolve=lambda _:resolved),client,GenerationGate())
    try:answer=await answerer.ask('应该怎样验证一份备份确实可以恢复？')
    finally:await answerer.close()
    assert not answer['insufficient_evidence'] and answer['citations']
    save(evidence/'answer.json',answer)
    assert originals=={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    return {'checks':['grounded_text_summary','image_reading','literal_qa_citations','unchanged_synthetic_originals'],
            'generation_requests':len(ledger['calls']),'accounted_yuan':sum(row['accounted_micros'] for row in ledger['calls'])/1e6}


def run_validation(resolved,*,continue_after_review=False):
    registry=SimpleNamespace(resolve=lambda _:resolved)
    resolved=resolve(registry,{'profile_id':resolved.profile_id})
    if resolved.profile.protocol!='openai_responses':raise RuntimeError('not_approved_openai_model')
    profile=resolved.profile.model_copy(update={'max_output_tokens':2048})
    resolved=ResolvedProfile(resolved.profile_id,profile,resolved.api_key,fingerprint(profile.model_dump()))
    LEDGER.parent.mkdir(exist_ok=True)
    lock=LEDGER.with_suffix('.lock')
    with lock.open('x',encoding='utf-8') as stream:stream.write(str(os.getpid()))
    evidence=ROOT/'.cache/openai-validation'/uuid4().hex;evidence.mkdir(parents=True)
    report={'status':'failed','model':resolved.profile.model,'budget_yuan':2,'max_calls':4,'max_output_tokens':2048}
    try:
        ledger=json.loads(LEDGER.read_text(encoding='utf-8')) if LEDGER.exists() else {'calls':[],'authorization':'user approved 2026-11-14; maximum CNY 2 and four generation requests'}
        if ledger['calls'] and not continue_after_review:raise RuntimeError('existing_validation_ledger_requires_review')
        if any(row['status']=='reserved' for row in ledger['calls']):raise RuntimeError('unfinished_validation_intent')
        if continue_after_review:ledger['explicit_continuation']='Reviewed previous failure; original costs and four-call/CNY-2 limits retained.'
        report.update(asyncio.run(exercise(resolved,evidence,ledger)),status='passed')
    except Exception as error:report['error_code']=getattr(error,'code',type(error).__name__)
    finally:
        save(evidence/'report.json',report);lock.unlink()
    print(json.dumps({**report,'report':str(evidence/'report.json')}))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--profile',default='openai-responses')
    parser.add_argument('--allow-paid',action='store_true')
    args=parser.parse_args()
    if not args.allow_paid:parser.error('Explicit --allow-paid is required (maximum CNY 2, four calls).')
    for key in list(os.environ):
        if key.startswith('MEMORY_OS_'):del os.environ[key]
    settings=Settings(_env_file=args.runtime/'.env',runtime_root=args.runtime)
    resolved=AIRegistry(settings).resolve(args.profile)
    return 0 if run_validation(resolved)['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
