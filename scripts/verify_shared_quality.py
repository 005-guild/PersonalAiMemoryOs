"""Seven synthetic quality cases, billed through the collection's shared monthly ledger."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.agents.configuration import AIRegistry
from app.agents.generation_gate import GenerationGate
from app.agents.prompts import build_template_prompts
from app.agents.transport import ModelClient
from app.config import Settings, resolve_database_url
from app.desktop.instance import SingleInstance
from app.models import OrganizationJob, utcnow
from app.repositories.database import Database
from app.services.organization.service import OrganizationService
from app.services.processing_v2 import validate_output_v2
from app.services.rag_answer import SYSTEM_PROMPT
from app.services.rag_answer_output import render_answer


async def exercise(service, output):
    corpus=json.loads((ROOT/'examples/quality/retrieval-cn.json').read_text(encoding='utf-8'))
    notes={row['key']:row for row in corpus['notes']}
    with service.store.transaction() as session:
        service.store.require_idle(session)
        control=service.store.control(session)
        if control['paused']:raise RuntimeError('organization_paused')
        config=control['config']
        job=OrganizationJob(mode='validation',status='running',selection=[],settings={**config,'initial_period':False})
        session.add(job);session.flush();job_id=job.id
    report={'job_id':job_id,'cases':[],'semantic_review':'pending','shared_monthly_budget':config['monthly_budget_yuan']}
    try:
        for key in ['database','experiment','injection']:
            note=notes[key]
            sources=[{'id':str(uuid5(NAMESPACE_URL,'memory-os-quality/'+key)),'version':1,'title':note['title'],
                      'content':note['body'],'author':'隔离自编样例','url':None}]
            system,user=build_template_prompts({'output_schema_version':2,
                'content':(ROOT/'app/prompts/zhihu_deep_analysis_v1.md').read_text(encoding='utf-8')},sources)
            value=await service.calls.generate(job_id,None,'acceptance-analysis-'+key,system,user,
                lambda raw:validate_output_v2(json.dumps(raw,ensure_ascii=False),sources))
            report['cases'].append({'id':'analysis-'+key,'output':value,'contract':'passed'})
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        for case in corpus['qa_review']:
            selected=case['required'] or ['plants']
            contexts=[{'chunk_id':key,'title':notes[key]['title'],'text':notes[key]['body']} for key in selected]
            value=await service.calls.generate(job_id,None,'acceptance-'+case['id'],SYSTEM_PROMPT,
                json.dumps({'question':case['question'],'contexts':contexts},ensure_ascii=False),
                lambda raw:render_answer(json.dumps(raw,ensure_ascii=False),contexts))
            report['cases'].append({'id':case['id'],'question':case['question'],'criteria':case['criteria'],
                                    'output':value,'contract':'passed'})
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        report['status']='awaiting_semantic_review'
        with service.store.transaction() as session:
            job=session.get(OrganizationJob,job_id);job.status='completed';job.finished_at=utcnow()
    except Exception as error:
        report.update(status='failed',error=getattr(error,'code',type(error).__name__))
        with service.store.transaction() as session:
            job=session.get(OrganizationJob,job_id);job.status='failed';job.error=report['error']
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'status':report['status'],'cases':len(report['cases']),'report':str(output/'report.json')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=ROOT/'dist/PersonalAiMemoryOs-0.6.6')
    parser.add_argument('--allow-paid',action='store_true')
    args=parser.parse_args()
    if not args.allow_paid:parser.error('Use --allow-paid for the approved shared monthly quality acceptance.')
    instance=SingleInstance(args.runtime)
    try:
        if not instance.owner:raise RuntimeError('Close the desktop normally before maintenance.')
        settings=Settings(_env_file=args.runtime/'.env',runtime_root=args.runtime)
        registry=AIRegistry(settings)
        database=Database(resolve_database_url(settings.database_url,root=args.runtime).render_as_string(hide_password=False));database.initialize()
        output=ROOT/'.cache/shared-quality';output.mkdir(exist_ok=True)
        async def run():
            client=ModelClient()
            try:
                service=OrganizationService(database,RLock(),settings,registry,client,GenerationGate(),'maintenance')
                return await exercise(service,output)
            finally:await client.aclose()
        try:print(json.dumps(asyncio.run(run()),ensure_ascii=False))
        finally:database.dispose()
    finally:instance.close()


if __name__=='__main__':main()
