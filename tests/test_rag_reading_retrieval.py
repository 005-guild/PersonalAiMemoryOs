"""Whole-note evidence, bounded candidates, stale-content guards and TEI failures."""

import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest
import yaml
from sqlalchemy import event

from app.main import create_app
from app.services.rag_reading import body_offset, build_reading, sections
from app.vector.chunking import render_note, split_document
from app.vector.errors import RagError
from app.vector.rerank import RerankClient, RerankOptions
from tests.test_rag_integration import Answers, Embeddings, Vectors, wait_for


def group(body, title="回避型依恋"):
    note = dict(id="note", version=1, title=title, summary="仅依据笔记。", body=body,
                category=None, tags=[], concepts=[], source_id=None, source_ids=[], sources=[], source=None, path=None)
    chunks = split_document(render_note(note))
    return dict(note=note, content_hash="a"*64, generation_id="gen", score=0.8,
                matches=[dict(ch, chunk_id=str(i), score=0.8) for i,ch in reversed(list(enumerate(chunks)))])


def test_5704_character_note_is_read_completely_in_original_order():
    body = "# 回避型依恋\n\n" + "作者的观点需要结合适用范围。\n" * 400
    body = body[:5704]
    notes, contexts = build_reading([group(body)])
    assert notes[0]["scope"] == "full"
    assert contexts[0]["text"].endswith(body)
    assert notes[0]["ranges"] == [[0, len(body)]]
    assert sum(len(c["text"]) for c in contexts) <= 12000


def test_headings_inside_code_are_not_section_boundaries():
    body = "# 第一节\n正文\n```python\n# 不是章节\nprint(1)\n```\n## 第二节\n结尾"
    parts = sections(body)
    assert len(parts) == 2
    assert "# 不是章节" in body[parts[0][0]:parts[0][1]]


def test_long_note_reads_relevant_section_and_budget_is_explicit():
    body = "# 无关章节\n" + "前言。"*2500 + "\n\n## 命中章节\n恢复演练可以验证备份。\n\n" + "后续。"*2500
    data = group(body)
    start = body_offset(data["note"]) + body.index("恢复演练")
    data["matches"] = [dict(start=start, end=start+20)]
    notes, contexts = build_reading([data])
    assert notes[0]["scope"] == "sections"
    assert "恢复演练" in contexts[0]["text"]
    assert len(contexts[0]["text"]) <= 12000
    assert notes[0]["read_chars"] < len(body)


@pytest.mark.parametrize("rows", [[], [{"index":0,"score":1}, {"index":0,"score":2}],
    [{"index":-1,"score":1},{"index":1,"score":2}], [{"index":0,"score":True},{"index":1,"score":2}],
    [{"index":0,"score":float("nan")},{"index":1,"score":2}], [{"index":0},{"index":1,"score":2}]])
def test_invalid_reranking_is_rejected_once(rows):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, content=json.dumps(rows))
    client = RerankClient(RerankOptions(enabled=True), transport=httpx.MockTransport(respond))
    with pytest.raises(RagError):
        asyncio.run(client.rank("query", ["a", "b"]))
    assert len(calls) == 1


def test_rerank_response_order_and_no_silent_truncation():
    def respond(request):
        body = json.loads(request.content)
        assert body["truncate"] is False and body["raw_scores"] is True
        return httpx.Response(200, json=[dict(index=1,score=-2),dict(index=0,score=5)])
    client = RerankClient(RerankOptions(enabled=True), transport=httpx.MockTransport(respond))
    assert asyncio.run(client.rank("query", ["a","b"])) == [5.0,-2.0]


def test_reranker_timeout_has_no_retry():
    calls=[]
    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("not public")
    client=RerankClient(RerankOptions(enabled=True),transport=httpx.MockTransport(respond))
    with pytest.raises(RagError) as failure:
        asyncio.run(client.rank("q",["a"]))
    assert failure.value.code == "rerank_timeout" and len(calls)==1


def configured(settings, root, **clients):
    directory=root/"config";directory.mkdir(exist_ok=True)
    for kind in ("embedding","ai"):
        p=dict(enabled=True,base_url="https://example.invalid/v1",model="fake",auth="none")
        p.update(dict(protocol="openai_embeddings",dimension=3) if kind=="embedding" else dict(protocol="openai_chat",response_format="json_object"))
        (directory/f"{kind}-providers.yml").write_text(yaml.safe_dump(dict(schema_version=1,default_profile="fake",profiles={"fake":p})),encoding="utf-8")
    return create_app(settings.model_copy(update=dict(rag_enabled=True,ai_enabled=True,rag_interval=3600)),
        embedding_client=Embeddings(),qdrant_client=Vectors(),model_client=clients.pop("model_client",Answers()),**clients)


def publish(client):
    wait_for(lambda: client.post("/api/v1/rag/index/run",json={}).status_code==202)
    def finished():
        status=client.get("/api/v1/rag/index/status?summary_only=true").json()
        return status["counts"]["pending"]==0 and not status["running"]
    wait_for(finished)


def test_grouped_retrieval_full_note_citations_and_no_vector_cache_reads(settings,isolated_project):
    class Ranker:
        options=RerankOptions(enabled=True)
        async def rank(self,query,texts):
            return [10 if "回避型" in text else -10 for text in texts]
    app=configured(settings,isolated_project,rerank_client=Ranker())
    with TestClient(app) as client:
        note=client.post("/api/v1/knowledge",json=dict(title="回避型依恋",body="# 观点\n恢复演练。"+"回避型依恋需要区分情境。"*300)).json()
        client.post("/api/v1/knowledge",json=dict(title="园艺",body="种植花草。"))
        publish(client)
        queries=[]
        def record(conn,cursor,statement,parameters,context,executemany): queries.append(statement.lower())
        event.listen(app.state.database.engine,"before_cursor_execute",record)
        result=client.post("/api/v1/rag/retrieve",json=dict(query="回避型",max_notes=5))
        event.remove(app.state.database.engine,"before_cursor_execute",record)
        assert result.status_code==200,result.text
        value=result.json()
        assert value["notes"][0]["knowledge_id"]==note["id"]
        assert len({item["knowledge_id"] for item in value["notes"]})==len(value["notes"])
        assert value["notes"][0]["scope"]=="full"
        assert not any("rag_index_jobs.vectors" in query for query in queries)
        answer=client.post("/api/v1/rag/answer",json=dict(question="回避型"))
        assert answer.status_code==200,answer.text
        assert answer.json()["citations"][0]["scope"]=="full"
        assert answer.json()["citations"][0]["context_id"]
        assert client.get("/api/v1/knowledge").json()["total"]==2
        # An edit invalidates the old publication before the worker catches up.
        client.patch("/api/v1/knowledge/"+note["id"],json=dict(expected_version=note["version"],body="修改后的正文。"))
        value=client.post("/api/v1/rag/retrieve",json=dict(query="回避型")).json()
        assert note["id"] not in {item["knowledge_id"] for item in value["notes"]}
        assert value["index_incomplete"]


def test_note_changed_during_answer_is_409_no_second_call(settings,isolated_project):
    class Mutating(Answers):
        calls=0
        async def generate(self,*args):
            self.calls+=1
            with app.state.sync_lock,app.state.database.session() as session:
                from app.models.content import Knowledge
                note=session.get(Knowledge,note_id)
                note.version+=1;note.body="新版";session.commit()
            return await super().generate(*args)
    model=Mutating()
    app=configured(settings,isolated_project,model_client=model)
    with TestClient(app) as client:
        note_id=client.post("/api/v1/knowledge",json=dict(title="备份",body="恢复演练。")).json()["id"]
        publish(client)
        response=client.post("/api/v1/rag/answer",json=dict(question="备份"))
        assert response.status_code==409 and response.json()["detail"]["code"]=="context_changed"
        assert model.calls==1


def test_rerank_setting_save_is_next_start_only_and_preserves_legacy_payloads(settings,isolated_project):
    from app.services.rag_settings import RAGSettingsService
    from app.api.rag_settings_schemas import RAGSettingsWrite
    service=RAGSettingsService(settings)
    before=service.describe()
    payload=dict(expected_revision=before["revision"],enabled=False,qdrant_url=before["qdrant_url"],profiles=[],reranker=dict(enabled=True,url="http://127.0.0.1:18081",model="BAAI/bge-reranker-v2-m3",revision="pinned",timeout_seconds=60))
    saved=service.save(RAGSettingsWrite.model_validate(payload))
    assert saved["restart_required"] and saved["reranker"]["enabled"]
    assert not saved["active"]["reranker"]["enabled"]
    payload.pop("reranker");payload["expected_revision"]=saved["revision"]
    assert service.save(RAGSettingsWrite.model_validate(payload))["reranker"]["revision"]=="pinned"
