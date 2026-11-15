"""Authenticated three-type export into a fresh isolated directory; zero model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image
from app.desktop.instance import SingleInstance
from app.services.zhihu_sync.browser import ZhihuBrowser
from app.services.zhihu_sync.configuration import Configuration
from app.services.zhihu_sync.runner import run_collection
from app.services.organization.inventory import inspect_directory


def fingerprint(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


class SelectedBrowser:
    unsupported_count=unlisted_count=0

    def __init__(self,browser,selected):
        self.browser,self.selected=browser,selected
        self.article_calls=self.image_calls=0

    def collection(self,url):
        return self.selected

    def article(self,identity):
        self.article_calls+=1
        return self.browser.article(identity)

    def image(self,url):
        self.image_calls+=1
        return self.browser.image(url)


def select_samples(identities,database):
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as connection:
        images=dict(connection.execute("SELECT identity,json_array_length(json_extract(snapshot,'$.images')) FROM organization_items"))
    selected=[]
    for kind in ('answer','article','pin'):
        candidates=[row for row in identities if row.resource_type==kind and 1<=images.get(kind+':'+row.external_id,0)<=3]
        if not candidates:raise RuntimeError('available_image_sample_missing_'+kind)
        selected.append(min(candidates,key=lambda row:(images[kind+':'+row.external_id],row.external_id)))
    return selected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=ROOT/'dist/PersonalAiMemoryOs-0.6.6')
    parser.add_argument('--execute',action='store_true',help='Export three existing favorites into a new .cache target, then verify deduplication')
    args=parser.parse_args()
    output=ROOT/'.cache/zhihu-media'/uuid4().hex;output.mkdir(parents=True)
    report={'status':'failed','model_calls':0,'newly_favorited_content':False,
            'scope':'Three existing accessible favorites, exported for the first time into a fresh isolated target.'}
    lease=SingleInstance(args.runtime)
    try:
        if not lease.owner:raise RuntimeError('Close the desktop normally before using its authenticated browser profile.')
        config=Configuration(args.runtime).load()
        original=Path(config.target_dir)
        before=fingerprint(original)
        database=args.runtime/'data/memory.db';database_before=hashlib.sha256(database.read_bytes()).hexdigest()
        with ZhihuBrowser(args.runtime) as browser:
            identities=browser.collection(config.collection_url)
            selected=select_samples(identities,database)
            report.update(collection_visible=len(identities),site_unlisted=browser.unlisted_count,
                selected=[{'type':row.resource_type,'id':row.external_id} for row in selected])
            if args.execute:
                target=output/'articles';target.mkdir()
                isolated=config.model_copy(update={'target_dir':str(target),'enabled':False})
                chosen=SelectedBrowser(browser,selected)
                report['first']=run_collection(isolated,chosen,lambda:False,lambda value:None)
                if report['first']['created']!=3 or report['first']['failed']:raise RuntimeError('three_type_export_incomplete')
                published=fingerprint(target);requests=(chosen.article_calls,chosen.image_calls)
                report['repeat']=run_collection(isolated,chosen,lambda:False,lambda value:None)
                assert report['repeat']['created']==0 and report['repeat']['skipped']==3
                assert fingerprint(target)==published and requests==(chosen.article_calls,chosen.image_calls)
                entries=inspect_directory(target)
                assert {(row['resource_type'],row['external_id']) for row in entries}=={(row.resource_type,row.external_id) for row in selected}
                for path in (target/'images').glob('*'):
                    with Image.open(path) as image:image.verify()
                report.update(images_verified=len(list((target/'images').glob('*'))),image_requests=chosen.image_calls,
                              original_files_unchanged=fingerprint(original)==before,
                              formal_database_unchanged=hashlib.sha256(database.read_bytes()).hexdigest()==database_before)
                assert report['original_files_unchanged'] and report['formal_database_unchanged']
                report['status']='passed'
            else:report['status']='previewed'
    except Exception as error:
        report['error']=str(error) if isinstance(error,RuntimeError) else type(error).__name__
        raise
    finally:
        lease.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'report':str(output/'report.json')},ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
