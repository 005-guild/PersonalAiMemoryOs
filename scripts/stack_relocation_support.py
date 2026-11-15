"""Strictly owned local runtime and collection snapshot helpers for migration drills."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import httpx
from scripts.verification_support import eventually, isolated_proxy_environment


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def file_hashes(folder):
    return {path.relative_to(folder).as_posix():digest(path) for path in folder.rglob('*') if path.is_file()}


class LocalOllama:
    def __init__(self,payload):
        self.payload=payload
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));self.port=listener.getsockname()[1]
        self.url=f'http://127.0.0.1:{self.port}'
        self.process=self.log=None

    def start(self):
        environment={k:v for k,v in os.environ.items() if not k.upper().startswith(('MEMORY_OS_','OLLAMA_'))}
        environment.update(isolated_proxy_environment())
        environment.update(OLLAMA_HOST=self.url,OLLAMA_MODELS=str(self.payload/'models'),OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1')
        self.log=(self.payload/'ollama.log').open('ab')
        self.process=subprocess.Popen([str(self.payload/'ollama/ollama.exe'),'serve'],cwd=self.payload,
            env=environment,stdout=self.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        def ready():
            if self.process.poll() is not None:raise RuntimeError('Owned Ollama exited')
            try:
                with httpx.Client(trust_env=False,timeout=2) as client:return client.get(self.url+'/api/version').json()
            except httpx.HTTPError:return None
        eventually(ready,timeout=45)
        return self.url

    def stop(self):
        if self.process and self.process.poll() is None:
            # No request is active here. Unload this isolated server's model before stopping its process.
            try:
                with httpx.Client(trust_env=False,timeout=30) as client:
                    client.post(self.url+'/api/embed',json={'model':'bge-m3','input':[],'keep_alive':0}).raise_for_status()
                    eventually(lambda:not client.get(self.url+'/api/ps').json()['models'],timeout=20)
            finally:
                self.process.terminate();self.process.wait(timeout=20)
        if self.log:self.log.close()
        self.process=self.log=None


def snapshot_collection(base,generation,folder):
    name=generation['collection'];metadata={'application':'personal-ai-memory-os','generation_id':generation['id'],'owner_id':generation['owner_id']}
    with httpx.Client(base_url=base,trust_env=False,timeout=60) as client:
        response=client.get('/collections/'+name);response.raise_for_status()
        assert response.json()['result']['config']['metadata']==metadata
        response=client.post('/collections/'+name+'/snapshots');response.raise_for_status()
        snapshot=response.json()['result']['name']
        if Path(snapshot).name!=snapshot or '/' in snapshot or '\\' in snapshot:raise ValueError('Invalid snapshot name')
        path=folder/'collection.snapshot'
        with client.stream('GET','/collections/'+name+'/snapshots/'+snapshot) as stream,path.open('xb') as output:
            stream.raise_for_status()
            for chunk in stream.iter_bytes():output.write(chunk)
        manifest={'collection':name,'metadata':metadata,'sha256':digest(path)}
        (folder/'snapshot.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        return manifest


def restore_collection(base,folder):
    manifest=json.loads((folder/'snapshot.json').read_text(encoding='utf-8'))
    path=folder/'collection.snapshot'
    assert digest(path)==manifest['sha256']
    name=manifest['collection']
    with httpx.Client(base_url=base,trust_env=False,timeout=90) as client:
        assert client.get('/collections/'+name).status_code==404,'Restore requires a fresh isolated collection'
        with path.open('rb') as stream:
            response=client.post('/collections/'+name+'/snapshots/upload',params={'wait':'true','priority':'snapshot'},
                                 files={'snapshot':(path.name,stream,'application/octet-stream')})
        response.raise_for_status()
        response=client.get('/collections/'+name);response.raise_for_status()
        assert response.json()['result']['config']['metadata']==manifest['metadata']


def points(base,name):
    with httpx.Client(trust_env=False,timeout=30) as client:
        response=client.post(base+'/collections/'+name+'/points/scroll',json={'limit':100,'with_vector':True,'with_payload':True})
        response.raise_for_status();result=response.json()['result']
        assert result['next_page_offset'] is None,'Fixture should fit in one page'
        return sorted(result['points'],key=lambda row:row['id'])
