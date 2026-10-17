"""Single-turn, snapshot-checked answers; no question history or note writes."""

import asyncio
import hashlib
import json
from pathlib import Path

from app.services.rag_answer_output import render_answer
from app.vector.errors import RagError

PROMPT_VERSION = "qa-v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "qa_v1.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
PROMPT_HASH = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
QA_CONTRACT = (PROMPT_PATH.parent / "rag_qa_contract_v1.md").read_text(encoding="utf-8")


class RagAnswerService:
    def __init__(self, search, registry, model_client, generation_gate):
        self.search, self.registry, self.model_client = search, registry, model_client
        self.gate = generation_gate
        self._closing = False
        self._tasks = set()

    async def ask(self, question: str, top_k: int = 5, profile_id: str | None = None, *, prompt_snapshot=None) -> dict:
        if self._closing:
            raise RagError(503, "rag_closing")
        resolved = self.registry.resolve(profile_id)
        if not self.gate.acquire(blocking=False):
            raise RagError(429, "generation_busy")
        task = asyncio.create_task(self._answer(question, top_k, resolved,
                                               dict(prompt_snapshot) if prompt_snapshot is not None else None))
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return await asyncio.shield(task)

    def _finished(self, task):
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def _answer(self, question, top_k, resolved, prompt=None):
        try:
            system = (QA_CONTRACT + "\n\n<answer_style>\n" + prompt["content"] +
                      "\n</answer_style>\n\n" + QA_CONTRACT) if prompt else SYSTEM_PROMPT
            prompt_hash = hashlib.sha256(system.encode("utf-8")).hexdigest()
            result = await self.search.search(question, top_k)
            contexts, length = [], 0
            for item in result["items"]:
                if length + len(item["text"]) > 12000:
                    break
                contexts.append(item)
                length += len(item["text"])
            if not contexts:
                answer = render_answer('{"insufficient_evidence":true,"paragraphs":[]}', [])
                usage = {}
            else:
                payload = {"question": question, "contexts": [
                    {field: item[field] for field in ("chunk_id", "title", "text")} for item in contexts
                ]}
                reply = await self.model_client.generate(
                    resolved, system, json.dumps(payload, ensure_ascii=False, allow_nan=False)
                )
                if not await asyncio.to_thread(self.search.validate_context, contexts):
                    raise RagError(409, "context_changed")
                answer = render_answer(reply.text, contexts)
                usage = reply.usage
            return {**answer, "index_incomplete": result["index_incomplete"],
                    "profile_id": resolved.profile_id, "model": resolved.profile.model,
                    "usage": usage, "prompt_version": str(prompt["version"]) if prompt else PROMPT_VERSION,
                    "prompt_hash": prompt_hash,
                    "prompt_template": {key: prompt[key] for key in
                        ("id", "version", "name", "purpose", "content_hash")} if prompt else None}
        finally:
            self.gate.release()

    async def close(self):
        self._closing = True
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks)),
                                 return_exceptions=True)
