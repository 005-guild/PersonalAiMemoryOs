"""Real same-host path relocation of a portable EXE, model files and Qdrant snapshot."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from uuid import uuid4
import httpx
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from scripts.benchmark_support import IsolatedQdrant
from scripts.stack_relocation_support import LocalOllama,file_hashes,snapshot_collection,restore_collection,points
from scripts.desktop_verification_support import FrozenDesktop
from scripts.local_rag_workflow import NOTES,QUERIES
from scripts.verification_support import eventually
from scripts.verify_desktop_upgrade import formal_storage_fingerprint


def wait_index(app):
    def ready():
        value=app.request('GET','/api/v1/rag/index/status?summary_only=true')
        if value.get('last_error') or value['counts']['failed']:raise RuntimeError('Isolated indexing failed')
        return value if value['counts']['published']==3 and not value['counts']['pending'] else None
    return eventually(ready,timeout=240)


def search(app,notes):
    for query,index in QUERIES:
        result=app.request('POST','/api/v1/rag/search',{'query':query,'top_k':5})
        assert result['items'] and result['items'][0]['knowledge_id']==notes[index]['id']
        assert not result['index_incomplete']


def embedding_config(desktop,url,digest):
    (desktop/'config').mkdir(exist_ok=True)
    value={'schema_version':1,'default_profile':'local','profiles':{'local':{'enabled':True,'protocol':'openai_embeddings',
        'base_url':url+'/v1','model':'bge-m3','model_revision':digest,'dimension':1024,'auth':'none','batch_size':1,'timeout_seconds':180}}}
    (desktop/'config/embedding-providers.yml').write_text(yaml.safe_dump(value),encoding='utf-8')


def environment_file(desktop,qdrant):
    (desktop/'.env').write_text('MEMORY_OS_AI_ENABLED=false\nMEMORY_OS_RAG_ENABLED=true\nMEMORY_OS_SYNC_ENABLED=true\n'
        'MEMORY_OS_DATABASE_URL=sqlite:///data/memory.db\nMEMORY_OS_KNOWLEDGE_DIR=knowledge\n'
        'MEMORY_OS_EMBEDDING_CONFIG_FILE=config/embedding-providers.yml\n'
        'MEMORY_OS_RAG_QDRANT_URL='+qdrant+'\n',encoding='utf-8')


def run(bundle):
    output=ROOT/'.cache/stack-relocation'/uuid4().hex;output.mkdir(parents=True)
    initial=output/'before';initial.mkdir()
    payload=initial/'runtime';payload.mkdir()
    report={'status':'failed','mode':'Same-host real EXE, copied Ollama/BGE-M3 and collection snapshot',
        'second_machine_tested':False,'paid_model_calls':0,'checks':[]}
    before=formal_storage_fingerprint()
    original_model_hashes=file_hashes(ROOT/'.cache/ollama/models')
    first=IsolatedQdrant();second=IsolatedQdrant();ollama=LocalOllama(payload);app=None
    try:
        required=sum(path.stat().st_size for directory in (ROOT/'.tools/ollama',ROOT/'.cache/ollama/models') for path in directory.rglob('*') if path.is_file())
        if shutil.disk_usage(output).free<required+4*1024**3:raise RuntimeError('Insufficient staging capacity')
        print('Copying isolated runtime and model files...',flush=True)
        shutil.copytree(ROOT/'.tools/ollama',payload/'ollama')
        shutil.copytree(ROOT/'.cache/ollama/models',payload/'models')
        model_hashes=file_hashes(payload/'models');tool_hashes=file_hashes(payload/'ollama')
        assert model_hashes==original_model_hashes and tool_hashes==file_hashes(ROOT/'.tools/ollama')
        desktop=initial/'desktop';shutil.copytree(bundle,desktop)
        ollama.start();url=first.start()
        with httpx.Client(trust_env=False,timeout=10) as client:
            model=next(row for row in client.get(ollama.url+'/api/tags').json()['models'] if row['name']=='bge-m3:latest')
        embedding_config(desktop,ollama.url,model['digest']);environment_file(desktop,url)
        app=FrozenDesktop(desktop,output);app.start()
        notes=[app.request('POST','/api/v1/knowledge',note) for note in NOTES]
        index=wait_index(app);search(app,notes)
        eventually(lambda:all(app.request('GET','/api/v1/knowledge/'+note['id'])['sync_status']=='synced' for note in notes),timeout=60)
        app.request_close();app.wait_closed();app=None
        database=(desktop/'data/memory.db').read_bytes();vault=file_hashes(desktop/'knowledge')
        generation=index['generation'];source_points=points(url,generation['collection'])
        snapshot_collection(url,generation,payload)
        first.stop();ollama.stop()
        report['checks']+=['independent_runtime_copy','real_bge_embedding','source_retrieval','consistent_database_vault_snapshot']
        moved=output/'中文 relocated stack'
        if not initial.resolve().is_relative_to(output.resolve()) or not moved.resolve().is_relative_to(output.resolve()) or moved.exists():
            raise RuntimeError('Invalid relocation target')
        initial.rename(moved)
        payload=moved/'runtime';desktop=moved/'desktop';ollama.payload=payload
        assert file_hashes(payload/'models')==model_hashes and file_hashes(payload/'ollama')==tool_hashes
        assert (desktop/'data/memory.db').read_bytes()==database and file_hashes(desktop/'knowledge')==vault
        ollama.start();url=second.start()
        restore_collection(url,payload)
        assert points(url,generation['collection'])==source_points
        environment_file(desktop,url)
        app=FrozenDesktop(desktop,output);app.start()
        index=wait_index(app)
        assert index['generation']['id']==generation['id']
        search(app,notes)
        assert len(app.request('GET','/api/v1/knowledge')['items'])==3
        app.request_close();app.wait_closed();app=None
        report.update(status='passed',model_digest=model['digest'],copied_model_files=len(model_hashes),
            copied_tool_files=len(tool_hashes),qdrant_points_verified=len(source_points),moved_vault_files=len(vault))
        report['checks']+=['whole_payload_relocated','qdrant_snapshot_restored_to_fresh_volume','point_vectors_payloads_identical',
                           'same_generation_after_move','real_queries_after_move','normal_exe_shutdown']
    except Exception as error:
        report['error']=type(error).__name__
        (output/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        if app:app.stop()
        for resource in (ollama,first,second):
            try:resource.stop()
            except Exception as error:report.update(status='failed',cleanup_error=type(error).__name__)
        report['formal_storage_unchanged']=before==formal_storage_fingerprint()
        report['shared_models_unchanged']=original_model_hashes==file_hashes(ROOT/'.cache/ollama/models')
        if not report['formal_storage_unchanged'] or not report['shared_models_unchanged']:report['status']='failed'
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'report':str(output/'report.json')}),flush=True)
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    args=parser.parse_args()
    if os.name!='nt':parser.error('Windows is required')
    from app.desktop.update_resources import read_manifest
    read_manifest(args.bundle.resolve())
    return run(args.bundle.resolve())


if __name__=='__main__':raise SystemExit(main())
