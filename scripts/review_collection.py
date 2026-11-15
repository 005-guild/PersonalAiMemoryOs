"""Apply an explicitly reviewed local classification manifest without model calls."""
import argparse
import json
from pathlib import Path
import sys
from threading import RLock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import select
from app.config import Settings
from app.models import Knowledge,OrganizationItem
from app.services.content import ContentService
from app.repositories.database import Database
from app.services.organization.service import OrganizationService
from app.agents.generation_gate import GenerationGate
from app.desktop.instance import SingleInstance


def apply_review(service,rows):
    with service.store.transaction() as session:
        service.store.require_idle(session)
        categories=service.store.control(session)['config']['taxonomy']
        for row in rows:
            if row['category'] not in categories or not row['reason'].strip():raise ValueError('invalid_review')
            item=session.scalar(select(OrganizationItem).where(OrganizationItem.knowledge_id==row['knowledge_id']))
            note=session.get(Knowledge,row['knowledge_id'])
            if not item or not note or item.error or note.deleted_at:raise ValueError('review_changed')
            if (item.result or {}).get('classification_review')==row:continue
            ContentService.require_version(note,row['expected_version'])
            if note.category!=row['category']:
                ContentService(session).update_knowledge(note.id,note.version,{'category':row['category']})
            item.result={**item.result,'classification_review':row}
        config=service.store.control(session)['config']
    service.publication.refresh(config)
    return {'reviewed':len(rows),'model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--runtime',type=Path,default=ROOT/'dist/PersonalAiMemoryOs-0.6.6')
    args=parser.parse_args()
    instance=SingleInstance(args.runtime)
    try:
        if not instance.owner:raise RuntimeError('Close the desktop normally before maintenance.')
        database=Database(f"sqlite:///{(args.runtime/'data/memory.db').resolve().as_posix()}")
        database.initialize()
        try:
            settings=Settings(_env_file=None,runtime_root=args.runtime,sync_enabled=False)
            service=OrganizationService(database,RLock(),settings,None,None,GenerationGate(),'maintenance')
            rows=json.loads(args.manifest.read_text(encoding='utf-8'))
            print(json.dumps(apply_review(service,rows)))
        finally:database.dispose()
    finally:instance.close()


if __name__=='__main__':main()
