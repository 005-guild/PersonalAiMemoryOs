"""Acceptance tooling enforces a durable budget without any provider requests."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from scripts import verify_v09_real_qa as tool


class Client:
    def __init__(self,fail=False):self.calls=0;self.fail=fail
    async def generate(self,*args):
        self.calls+=1
        if self.fail:raise RuntimeError("do not serialize secret details")
        return SimpleNamespace(usage={"output_tokens":2})


def test_unknown_or_failed_call_is_durably_counted_before_request(tmp_path,monkeypatch):
    path=tmp_path/"ledger.json";monkeypatch.setattr(tool,"LEDGER",path)
    ledger={"calls":[]};client=Client(fail=True)
    with pytest.raises(RuntimeError):
        asyncio.run(tool.BudgetModel(client,ledger).generate(SimpleNamespace(profile=SimpleNamespace(model="test")),"s","u"))
    saved=json.loads(path.read_text(encoding="utf-8"))
    assert client.calls==1 and len(saved["calls"])==1
    assert saved["calls"][0]["status"]=="failed_or_unknown"
    assert "secret" not in path.read_text(encoding="utf-8")


def test_exhausted_budget_cannot_reach_model(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,"LEDGER",tmp_path/"ledger.json")
    client=Client();ledger={"calls":[{}, {}, {}]}
    with pytest.raises(RuntimeError,match="exhausted"):
        asyncio.run(tool.BudgetModel(client,ledger).generate(None,"s","u"))
    assert client.calls==0


def test_success_records_available_usage(tmp_path,monkeypatch):
    path=tmp_path/"ledger.json";monkeypatch.setattr(tool,"LEDGER",path)
    client=Client();ledger={"calls":[]}
    asyncio.run(tool.BudgetModel(client,ledger).generate(SimpleNamespace(profile=SimpleNamespace(model="test")),"s","u"))
    assert json.loads(path.read_text())["calls"][0]["usage"]["output_tokens"]==2
