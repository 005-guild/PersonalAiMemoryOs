"""Import and adopt approved cached pilot summaries in an idle installation."""
import argparse
import json
import sys
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings, resolve_database_url
from app.models import Knowledge, OrganizationItem
from app.repositories.database import Database
from app.services.organization.service import OrganizationService
from app.services.organization.quality import QualityService
from app.services.organization.contracts import fingerprint
from app.services.organization.quality_contract import validate, markdown
from scripts.summary_quality.storage import load, verify_sources


def adopt(service, directory):
    packet=load(directory/'samples.json'); results=load(directory/'results.json')
    if packet['packet_hash'] != fingerprint({k:v for k,v in packet.items() if k!='packet_hash'}):
        raise RuntimeError('pilot_packet_modified')
    if Path(service.store.database.url.database).resolve() != Path(packet['database']).resolve():
        raise RuntimeError('pilot_database_mismatch')
    with service.store.transaction() as session:
        service.store.require_idle(session)
        installed=service.store.control(session).get('approved_pilot')==packet['packet_hash']
    if not installed:
        verify_sources(packet)
        ledger=load(directory.parent/'budget.json')
        # The original ledger remains the authoritative provenance, copied only as accounting metadata.
        rows=ledger['calls']
        with service.store.transaction() as session:
            control=service.store.control(session)
            costs=list(control.get('external_costs',[]))
            identity='summary-pilot-'+packet['packet_hash']
            if not any(row['id']==identity for row in costs):
                costs.append({'id':identity,'period':'2026-11','accounted_micros':sum(row['accounted_micros'] for row in rows),
                              'calls':len(rows),'provenance':str(directory.parent/'budget.json')})
            for sample in packet['samples']:
                item=session.get(OrganizationItem,sample['item_id'])
                candidate=validate(json.dumps(results[sample['identity']]['candidate'],ensure_ascii=False),sample)
                item.result={**item.result,'quality_candidate':{'id':fingerprint({'packet':packet['packet_hash'],'identity':sample['identity']}),
                    'base_version':sample['current']['version'],'input_hash':sample['input_hash'],'value':candidate,
                    'markdown':markdown(candidate),'provenance':{'packet':packet['packet_hash'],'request_hash':results[sample['identity']]['request_hash']}}}
            control.update(quality_enabled=True,approved_pilot=packet['packet_hash'],external_costs=costs)
            service.store.set_control(session,control)
    quality=QualityService(service)
    adopted=[]
    for sample in packet['samples']:
        view=quality.view(sample['knowledge_id'])
        if view['candidate']:
            quality.adopt(sample['knowledge_id'],view['candidate']['base_version'],view['candidate']['id'])
        adopted.append(sample['knowledge_id'])
    return {'adopted':len(adopted),'additional_model_calls':0,'quality_enabled':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=ROOT/'dist/PersonalAiMemoryOs-0.6.6')
    parser.add_argument('--directory',type=Path,default=ROOT/'.cache/summary-quality/pilot-20261115')
    args=parser.parse_args()
    from app.desktop.instance import SingleInstance
    # The same installation mutex is held throughout maintenance.
    instance=SingleInstance(args.runtime)
    if not instance.owner:
        instance.close()
        raise RuntimeError('Close the desktop normally before importing the approved pilot.')
    settings=Settings(_env_file=None,runtime_root=args.runtime,database_url=f"sqlite:///{(args.runtime/'data/memory.db').resolve().as_posix()}")
    database=Database(settings.database_url);database.initialize()
    try:
        from app.agents.generation_gate import GenerationGate
        service=OrganizationService(database,RLock(),settings,None,None,GenerationGate(),'maintenance')
        print(json.dumps(adopt(service,args.directory),ensure_ascii=False))
    finally:
        database.dispose()
        instance.close()


if __name__=='__main__':main()
