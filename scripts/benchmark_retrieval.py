"""Compare old/new retrieval over copied, stopped synthetic capacity fixtures."""

import argparse
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import event
import yaml

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.config import Settings
from app.main import create_app
from app.repositories.migrations import upgrade_database
from app.repositories.rag import collection_metadata
from scripts.benchmark_support import IsolatedQdrant, SyntheticEmbedding, timings
from scripts.local_rag_support import ForbiddenGeneration
from scripts.v05_acceptance import storage_fingerprint
from scripts.verification_support import isolated_proxy_environment


def digest(path):
    return hashlib.file_digest(path.open("rb"),"sha256").hexdigest()


async def upload(client,source,generation):
    await client.ensure_collection(generation["collection"],generation["dimension"],collection_metadata(generation))
    with closing(sqlite3.connect(source)) as connection:
        rows=connection.execute("select j.knowledge_id,j.content_hash,j.chunks,j.vectors from rag_index_jobs j join rag_note_index_states s on s.published_job_id=j.id where j.status='published'")
        pending=[]
        for note,digest,chunks,vectors in rows:
            for chunk,vector in zip(json.loads(chunks),json.loads(vectors)):
                pending.append(dict(id=chunk["id"],vector=vector,payload=dict(knowledge_id=note,content_hash=digest,generation_id=generation["id"])))
                if len(pending)>=128:await client.upsert(generation["collection"],pending);pending=[]
        await client.upsert(generation["collection"],pending)


def run(baseline):
    baseline=baseline.resolve()
    if not baseline.is_relative_to((ROOT/".cache/capacity-baseline").resolve()):raise ValueError("Synthetic cache path required")
    output=ROOT/".cache/retrieval-capacity"/uuid4().hex;output.mkdir(parents=True)
    resource=IsolatedQdrant();before=storage_fingerprint();report=dict(status="failed",stages=[],paid_calls=0,embedding_inference_calls=0)
    environment={key:value for key,value in os.environ.items() if not key.upper().startswith("MEMORY_OS_")}
    environment.update(isolated_proxy_environment())
    try:
        url=resource.start()
        with patch.dict(os.environ,environment,clear=True):
            for source_root in sorted(baseline.glob("stage-*")):
                source=source_root/"data/memory.db";original=digest(source)
                profile=source_root/"config/embedding-providers.yml"
                document=yaml.safe_load(profile.read_text(encoding="utf-8"))
                declared=document["profiles"][document["default_profile"]]
                if declared["model"]!="synthetic-hash-v1" or declared["base_url"]!="http://127.0.0.1:1/v1":raise ValueError("Only synthetic fixture profiles are allowed")
                target=output/source_root.name;(target/"data").mkdir(parents=True);(target/"config").mkdir()
                shutil.copy2(profile,target/"config/embedding-providers.yml")
                with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as first,closing(sqlite3.connect(target/"data/memory.db")) as second:first.backup(second)
                settings=Settings(_env_file=None,runtime_root=target,database_url="sqlite:///"+(target/"data/memory.db").as_posix(),rag_enabled=True,rag_qdrant_url=url,sync_enabled=False,log_level="ERROR")
                upgrade_database(settings.database_url)
                forbidden=ForbiddenGeneration();app=create_app(settings,embedding_client=SyntheticEmbedding(),model_client=forbidden)
                with patch.object(app.state.rag_worker,"start",lambda:None),TestClient(app) as api:
                    generation=app.state.rag_retrieval.snapshot()[0]
                    api.portal.call(upload,app.state.qdrant_client,target/"data/memory.db",generation)
                    metrics=dict(notes=api.get("/api/v1/ui/knowledge").json()["total"])
                    for endpoint,samples in (("search",3),("retrieve",5)):
                        durations=[];queries=[]
                        def record(conn,cursor,statement,parameters,context,executemany):queries.append(statement.lower())
                        event.listen(app.state.database.engine,"before_cursor_execute",record)
                        try:
                            for _ in range(samples):
                                start=time.perf_counter();response=api.post("/api/v1/rag/"+endpoint,json=dict(query="隔离容量测量"));durations.append(time.perf_counter()-start)
                                assert response.status_code==200,response.text
                        finally:event.remove(app.state.database.engine,"before_cursor_execute",record)
                        metrics[endpoint]=timings(durations)
                        metrics[endpoint+"_vector_cache_selects"]=sum("rag_index_jobs.vectors" in query for query in queries)
                    assert metrics["retrieve_vector_cache_selects"]==0
                    assert forbidden.calls==0
                metrics["source_unchanged"]=digest(source)==original;assert metrics["source_unchanged"]
                report["stages"].append(metrics)
                print(json.dumps(metrics),flush=True)
        report["status"]="measured"
    finally:
        resource.stop();report["formal_storage_unchanged"]=before==storage_fingerprint()
        (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(dict(status=report["status"],report=str(output/"report.json"))),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--baseline",required=True,type=Path)
    run(parser.parse_args().baseline)
