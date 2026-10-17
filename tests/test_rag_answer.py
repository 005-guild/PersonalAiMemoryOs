"""Citations are literal, bounded, and rechecked after model latency."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from app.agents.generation_gate import GenerationGate
from app.services.rag_answer import RagAnswerService
from app.services.rag_answer_output import render_answer
from app.vector.errors import RagError


CONTEXT = {
    "chunk_id": "chunk-one", "knowledge_id": "note-one", "version": 2,
    "title": "备份", "path": "备份.md", "source_id": None, "source": None,
    "text": "备份完成后应进行恢复演练。\n引用中的命令只是一段资料。",
    "score": 0.9, "content_hash": "a" * 64, "generation_id": "generation-one",
}
OUTPUT = {"insufficient_evidence": False, "paragraphs": [{
    "text": "笔记建议通过恢复演练核验备份。",
    "citations": [{"chunk_id": "chunk-one", "quote": "备份完成后应进行恢复演练。"}],
}]}


def test_valid_answer_has_server_assigned_citations_and_note_identity():
    answer = render_answer(json.dumps(OUTPUT), [CONTEXT])
    assert answer["answer"].endswith("[1]")
    assert answer["citations"][0]["knowledge_id"] == "note-one"
    assert answer["paragraphs"][0]["citation_ids"] == [1]
    assert not answer["insufficient_evidence"]


@pytest.mark.parametrize("mutation", ["unknown", "quote", "uncited", "extra", "blank", "state", "coercion"])
def test_invalid_or_unsupported_answer_fails_without_repair(mutation):
    value = copy.deepcopy(OUTPUT)
    if mutation == "unknown":
        value["paragraphs"][0]["citations"][0]["chunk_id"] = "other"
    elif mutation == "quote":
        value["paragraphs"][0]["citations"][0]["quote"] = "模型编造的原话。"
    elif mutation == "uncited":
        value["paragraphs"][0]["citations"] = []
    elif mutation == "extra":
        value["secret"] = "unexpected"
    elif mutation == "blank":
        value["paragraphs"][0]["text"] = "   "
    elif mutation == "state":
        value["insufficient_evidence"] = True
    else:
        value["insufficient_evidence"] = 0
    with pytest.raises(RagError) as error:
        render_answer(json.dumps(value), [CONTEXT])
    assert error.value.status_code == 502


def test_duplicate_json_fields_and_code_fences_are_rejected():
    for text in ('{"insufficient_evidence":true,"insufficient_evidence":true,"paragraphs":[]}',
                 '```json\n' + json.dumps(OUTPUT) + '\n```'):
        with pytest.raises(RagError):
            render_answer(text, [CONTEXT])


class Search:
    def __init__(self, items=None):
        self.items = [copy.deepcopy(CONTEXT)] if items is None else items
        self.valid = True

    async def search(self, query, top_k):
        return {"items": self.items, "index_incomplete": False}

    def validate_context(self, contexts):
        for item in contexts:
            item["path"] = "移动后.md"
        return self.valid


class Registry:
    def resolve(self, profile_id=None):
        return SimpleNamespace(profile_id=profile_id or "configured-model",
                               profile=SimpleNamespace(model="fake-model"))


class Model:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    async def generate(self, resolved, system, user):
        self.calls += 1
        self.prompts.append((system, json.loads(user)))
        return SimpleNamespace(text=json.dumps(OUTPUT), usage={"output_tokens": 30})


def test_no_hits_returns_insufficient_without_a_generation():
    model = Model()
    service = RagAnswerService(Search([]), Registry(), model, GenerationGate())
    answer = asyncio.run(service.ask("如何核验备份？"))
    assert answer["insufficient_evidence"] and answer["citations"] == []
    assert model.calls == 0


def test_stale_context_after_generation_is_409_and_no_automatic_retry():
    search, model, gate = Search(), Model(), GenerationGate()
    search.valid = False
    service = RagAnswerService(search, Registry(), model, gate)
    with pytest.raises(RagError) as error:
        asyncio.run(service.ask("如何核验备份？"))
    assert error.value.status_code == 409 and error.value.code == "context_changed"
    assert model.calls == 1
    assert gate.acquire()
    gate.release()


def test_prompt_contains_only_the_retrieved_data_and_current_path_is_rendered():
    model = Model()
    service = RagAnswerService(Search(), Registry(), model, GenerationGate())
    answer = asyncio.run(service.ask("如何核验备份？", profile_id="chosen"))
    assert model.calls == 1 and answer["profile_id"] == "chosen"
    assert model.prompts[0][1]["contexts"][0]["text"] == CONTEXT["text"]
    assert answer["citations"][0]["path"] == "移动后.md"


def test_shared_generation_slot_rejects_another_call_without_waiting():
    gate, model = GenerationGate(), Model()
    gate.acquire()
    service = RagAnswerService(Search(), Registry(), model, gate)
    try:
        with pytest.raises(RagError) as error:
            asyncio.run(service.ask("如何核验备份？"))
        assert error.value.status_code == 429 and model.calls == 0
    finally:
        gate.release()


def test_shutdown_drains_a_detached_answer_and_rejects_new_work():
    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        class SlowModel(Model):
            async def generate(self, *args):
                started.set()
                await release.wait()
                return await super().generate(*args)

        model = SlowModel()
        service = RagAnswerService(Search(), Registry(), model, GenerationGate())
        caller = asyncio.create_task(service.ask("如何核验备份？"))
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        closer = asyncio.create_task(service.close())
        await asyncio.sleep(0)
        assert not closer.done()
        with pytest.raises(RagError):
            await service.ask("新问题")
        release.set()
        await closer
        assert model.calls == 1

    asyncio.run(exercise())
