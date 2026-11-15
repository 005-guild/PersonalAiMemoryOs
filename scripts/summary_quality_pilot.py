"""Prepare, explicitly generate, or report the fixed ten-article summary pilot."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.agents.configuration import AIRegistry
from app.agents.transport import ModelClient
from app.config import Settings,resolve_database_url
from app.services.organization.contracts import fingerprint
from scripts.summary_quality.storage import freeze,load,save,verify_sources
from scripts.summary_quality.budget import Budget,budget_lock
from scripts.summary_quality.generation import pilot_profile,user_input,validate
from scripts.summary_quality.report import report

BUDGET_ROOT=ROOT/'.cache/summary-quality'
PROMPT=ROOT/'app/prompts/collection_quality_pilot_v1.md'


async def generate(directory,resolved,client):
    packet=load(directory/'samples.json')
    expected=packet['packet_hash']
    if fingerprint({key:value for key,value in packet.items() if key!='packet_hash'})!=expected: raise RuntimeError('pilot_packet_modified')
    verify_sources(packet)
    results=load(directory/'results.json') if (directory/'results.json').exists() else {}
    budget=Budget(BUDGET_ROOT,client,resolved);system=PROMPT.read_text(encoding='utf-8')
    for sample in packet['samples']:
        verify_sources(packet)
        identity=sample['identity']
        request_hash=''
        try:
            user=user_input(sample)
            request_hash=fingerprint({'system':system,'user':user,'profile':resolved.fingerprint,'output_tokens':4096,'input_hash':sample['input_hash']})
            raw,row=await budget.generate(request_hash,system,user)
            try: candidate=validate(raw,sample)
            except (ValueError,KeyError,TypeError):
                budget.validated(row,False);raise RuntimeError('pilot_invalid_evidence_or_output') from None
            budget.validated(row,True)
            results[identity]={'status':'succeeded','candidate':candidate,'request_hash':request_hash,
                'call_number':row['number'],'accounted_micros':row['accounted_micros']}
        except Exception as error:
            previous=budget.cached(request_hash)
            results[identity]={'status':'deferred','error':getattr(error,'code',str(error)) if isinstance(error,RuntimeError) else type(error).__name__,
                'accounted_micros':previous['accounted_micros'] if previous else 0}
        save(directory/'results.json',results)
        status=report(directory,BUDGET_ROOT)
        print(json.dumps({'finished':len(results),'generated':status['generated'],'accounted_yuan':status['accounted_yuan']}),flush=True)
        if results[identity].get('error') in {'pilot_budget_exhausted','pilot_call_limit'}:break
    verify_sources(packet)
    return report(directory,BUDGET_ROOT)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','generate','report'])
    parser.add_argument('--runtime',type=Path,default=ROOT/'dist/PersonalAiMemoryOs-0.6.6')
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--allow-paid',action='store_true',help='Use the approved shared CNY 5 / ten-call pilot authorization')
    args=parser.parse_args()
    for key in list(os.environ):
        if key.startswith('MEMORY_OS_'):del os.environ[key]
    directory=(args.directory or BUDGET_ROOT/('run-'+uuid4().hex)).resolve()
    if not directory.is_relative_to(BUDGET_ROOT.resolve()) or directory==BUDGET_ROOT.resolve():parser.error('Output must be a child of .cache/summary-quality')
    if args.command=='prepare':
        directory.mkdir(parents=True,exist_ok=False)
        freeze(args.runtime/'data/memory.db',directory)
        status=report(directory,BUDGET_ROOT)
    elif args.command=='report':status=report(directory,BUDGET_ROOT)
    else:
        if not args.allow_paid:parser.error('Generation requires --allow-paid (shared maximum CNY 5, ten generation calls).')
        settings=Settings(_env_file=args.runtime/'.env',runtime_root=args.runtime)
        if Path(resolve_database_url(settings.database_url,root=args.runtime).database).resolve()!=Path(load(directory/'samples.json')['database']).resolve():
            raise RuntimeError('pilot_runtime_database_mismatch')
        resolved=pilot_profile(AIRegistry(settings))
        async def run():
            client=ModelClient()
            try:return await generate(directory,resolved,client)
            finally:await client.aclose()
        with budget_lock(BUDGET_ROOT):status=asyncio.run(run())
    print(json.dumps({'directory':str(directory),**status},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
