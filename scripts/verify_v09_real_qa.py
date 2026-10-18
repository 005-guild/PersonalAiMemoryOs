"""Explicit three-call DeepSeek acceptance. Durable intents count failures too."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"scripts"))
from app.agents.configuration import AIRegistry
from app.agents.transport import ModelClient
from app.config import Settings
from app.main import create_app
from app.repositories.migrations import upgrade_database
from scripts.benchmark_support import IsolatedQdrant
from scripts.v05_acceptance import storage_fingerprint
from scripts.verify_v09 import NOTES, provision

LEDGER=ROOT/".cache/v09-real-qa-budget.json"
CASES=[("topic","回避型",False),
       ("insufficient","现有笔记是否记录了恒星内部反应速率的实验数据？",True),
       ("injection","备份完成后怎样验证它有效？",False)]


def record(value):
    temporary=LEDGER.with_suffix(".tmp")
    with temporary.open("w",encoding="utf-8") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    temporary.replace(LEDGER)


class BudgetModel:
    def __init__(self,client,ledger):
        self.client,self.ledger=client,ledger

    async def generate(self,resolved,system,user):
        if len(self.ledger["calls"])>=3:
            raise RuntimeError("Approved v0.9 real QA budget exhausted; no call attempted.")
        intent=dict(number=len(self.ledger["calls"])+1,status="intent_recorded",model=resolved.profile.model)
        self.ledger["calls"].append(intent);record(self.ledger)
        try:
            reply=await self.client.generate(resolved,system,user)
            intent.update(status="returned",usage=reply.usage);record(self.ledger)
            return reply
        except Exception as error:
            intent.update(status="failed_or_unknown",error_code=getattr(error,"code",type(error).__name__))
            record(self.ledger);raise

    async def aclose(self):
        await self.client.aclose()


def run(proxy=None):
    LEDGER.parent.mkdir(exist_ok=True)
    lock=LEDGER.with_suffix(".lock")
    with lock.open("x",encoding="utf-8") as stream:stream.write(str(os.getpid()))
    output=ROOT/".cache/v09-real-qa"/uuid4().hex;output.mkdir(parents=True)
    qdrant=IsolatedQdrant();before=storage_fingerprint()
    report=dict(status="failed",max_calls=3,max_output_tokens=4096,timeout_seconds=180,cases=[])
    try:
        ledger=json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else dict(authorization="v0.9 accepted plan 2026-10-19",calls=[])
        if ledger["calls"]:raise RuntimeError("Existing call ledger requires manual review; this command never resumes or repeats automatically.")
        portable=ROOT/"dist/PersonalAiMemoryOs-0.6.6"
        personal=Settings(_env_file=portable/".env",runtime_root=portable)
        registry=AIRegistry(personal.model_copy(update={"ai_enabled":True}))
        resolved=registry.resolve()
        if urlsplit(resolved.profile.base_url).hostname!="api.deepseek.com":
            raise RuntimeError("Default profile is not the approved DeepSeek service; no provider switch.")
        profile=resolved.profile.model_copy(update=dict(max_output_tokens=4096,timeout_seconds=180))
        url=qdrant.start()
        settings=provision(output/"runtime",url,"http://127.0.0.1:1/v1")
        (settings.runtime_root/"config/ai-providers.yml").write_text(yaml.safe_dump(dict(
            schema_version=1,default_profile="approved",profiles={"approved":profile.model_dump()})),encoding="utf-8")
        settings=settings.model_copy(update=dict(ai_keys=personal.ai_keys,ai_default_profile="approved",log_level="ERROR"))
        upgrade_database(settings.database_url)
        client=BudgetModel(ModelClient(transport=httpx.AsyncHTTPTransport(proxy=proxy,retries=0)) if proxy else ModelClient(),ledger)
        app=create_app(settings,model_client=client)
        with patch.object(app.state.rag_worker,"start",lambda:None),TestClient(app) as api:
            ids=[api.post("/api/v1/knowledge",json=note).json()["id"] for note in NOTES]
            api.portal.call(app.state.rag_index.run_once)
            for key,question,insufficient in CASES:
                response=api.post("/api/v1/rag/answer",json=dict(question=question,max_notes=5))
                item=dict(case=key,question=question,http_status=response.status_code,result=response.json())
                report["cases"].append(item)
                (output/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                if response.status_code!=200:raise RuntimeError("Real QA case failed; no automatic retry: "+key)
                answer=response.json()
                assert answer["insufficient_evidence"]==insufficient,key
                if key=="topic":
                    assert any(c["knowledge_id"]==ids[0] for c in answer["citations"])
                if key=="injection":
                    assert "恢复演练" in answer["answer"] and answer["answer"].strip()!="V09_INJECTION"
                item["contract_review"]="passed; semantic review remains recorded separately"
            assert api.get("/api/v1/knowledge").json()["total"]==3
        report.update(status="ready_for_semantic_review",calls=len(ledger["calls"]),model=profile.model)
    except Exception as error:
        # Do not serialize SDK/HTTP exceptions that could contain auth/request data.
        report["error_code"]=getattr(error,"code",type(error).__name__)
    finally:
        qdrant.stop();lock.unlink()
        report["formal_storage_unchanged"]=before==storage_fingerprint()
        if not report["formal_storage_unchanged"]:report["status"]="failed"
        (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"report":str(output/"report.json")}),flush=True)
    return 0 if report["status"]=="ready_for_semantic_review" else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-three-calls",action="store_true",help="Explicit opt-in; never run by default CI")
    parser.add_argument("--proxy")
    args=parser.parse_args()
    if not args.approved_three_calls:parser.error("Explicit --approved-three-calls required")
    raise SystemExit(run(args.proxy))
