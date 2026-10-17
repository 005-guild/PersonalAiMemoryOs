"""Generate durable drafts outside transactions, then adopt them atomically."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.agents.errors import AIError
from app.agents.generation_gate import GenerationGate
from app.agents.prompts import PROMPT_HASH, PROMPT_VERSION, build_prompts, build_template_prompts
from app.agents.configuration import ResolvedProfile
from app.models import ProcessingRun, utcnow
from app.repositories.processing import ProcessingRepository
from app.services.content import ContentError, ContentService
from app.services.processing_output import OUTPUT_SCHEMA_VERSION, render_proposal, validate_output
from app.services.processing_records import input_hash, run_dict, source_snapshot
from app.services.processing_v2 import validate_output_v2, render_proposal_v2
from app.services.prompt_templates import PromptTemplateService, snapshot_template
from app.services.processing_limits import require_source_input


class ProcessingFailure(Exception):
    """Safe API failure metadata; never includes an upstream body or credential."""

    def __init__(self, status_code: int, code: str, run_id: str | None = None) -> None:
        super().__init__(code)
        self.status_code, self.code, self.run_id = status_code, code, run_id


class ProcessingService:
    def __init__(self, database, lock, registry, model_client, generation_gate=None) -> None:
        self.database, self.lock = database, lock
        self.registry, self.model_client = registry, model_client
        self._gate = generation_gate if generation_gate is not None else GenerationGate()
        self._tasks: set[asyncio.Task] = set()
        self._closing = False
        self.templates = PromptTemplateService(database, lock)
        from app.services.processing_batches import ProcessingBatchService
        self.batches = ProcessingBatchService(self)

    async def generate(self, source_id: str, expected_source_version: int,
                       profile_id: str | None = None, *, prompt_template_id=None,
                       prompt_template_version=None, generation_settings=None) -> dict:
        if self._closing:
            raise ProcessingFailure(503, "processing_unavailable")
        resolved = self.registry.resolve(profile_id)
        if generation_settings is not None:
            profile = resolved.profile.model_copy(update=dict(generation_settings))
            resolved = ResolvedProfile(resolved.profile_id, profile, resolved.api_key, input_hash(profile.model_dump()))
        prompt = None
        if prompt_template_version is not None and prompt_template_id is None:
            raise ContentError(422, "Specify the prompt ID when selecting a revision.")
        if prompt_template_id:
            prompt = await asyncio.to_thread(self._prompt, prompt_template_id, prompt_template_version)
        if not self._gate.acquire(blocking=False):
            raise ProcessingFailure(429, "processing_busy")
        task = asyncio.create_task(self._generate(source_id, expected_source_version, resolved, prompt))
        self._tasks.add(task)
        task.add_done_callback(self._finished_task)
        # A disconnected caller must not leave an unqueryable half-finished run.
        return await asyncio.shield(task)

    def _prompt(self, identifier, version):
        self.templates.ensure_builtins()
        with self.lock, self.database.session() as session:
            prompt = snapshot_template(session, identifier, version)
            prompt["system_prompt"] = build_template_prompts(prompt, [])[0]
            return prompt

    def _finished_task(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve a detached caller's failure without logging raw data.

    async def _generate(self, source_id: str, expected_source_version: int, resolved, prompt=None) -> dict:
        run_id = None
        try:
            run = await asyncio.to_thread(self._begin, source_id, expected_source_version, resolved, prompt)
            run_id = run["id"]
            return await self.execute_run(run, resolved)
        except (SQLAlchemyError, RuntimeError):
            raise ProcessingFailure(503, "database_unavailable", run_id) from None
        finally:
            self._gate.release()

    async def execute_run(self, run, resolved):
        """One already-persisted call intent; caller owns the shared generation slot."""
        reply = None
        try:
            snapshots = run["source_snapshots"]
            if run.get("prompt_snapshot"):
                prompts = build_template_prompts(run["prompt_snapshot"], snapshots)
            else:
                prompts = build_prompts(run["source_snapshot"])
            reply = await self.model_client.generate(resolved, *prompts)
            if run["output_schema_version"] == 2:
                result = validate_output_v2(reply.text, snapshots)
                proposal = render_proposal_v2(result, snapshots)
            else:
                result = validate_output(reply.text, run["source_snapshot"])
                proposal = render_proposal(result, run["source_snapshot"])
                if len(snapshots) > 1:
                    proposal.pop("source_id", None)
                    proposal["source_ids"] = [source["id"] for source in snapshots]
        except AIError as error:
            usage = getattr(reply, "usage", None) if reply is not None else error.usage
            finish = getattr(reply, "finish_reason", None) if reply is not None else error.finish_reason
            stage = ("validation" if error.code in {"invalid_output", "invalid_evidence"} else
                     "refusal" if error.code == "model_refused" else
                     "finish" if error.code == "model_output_truncated" else
                     "protocol" if error.code in {"invalid_model_response", "ai_response_too_large"} else "transport")
            await asyncio.to_thread(self._fail, run["id"], error.code, stage, usage, finish)
            raise ProcessingFailure(error.status_code, error.code, run["id"]) from None
        except Exception:
            await asyncio.to_thread(self._fail, run["id"], "processing_failed", "system",
                                    getattr(reply, "usage", None), getattr(reply, "finish_reason", None))
            raise ProcessingFailure(502, "processing_failed", run["id"]) from None
        # A database failure while publishing must retain the running intent so
        # restart recovery reports interruption rather than repeating the call.
        return await asyncio.to_thread(self._ready, run["id"], result, proposal, reply.usage,
                                        getattr(reply, "finish_reason", None))

    def _begin(self, source_id: str, expected_version: int, resolved, prompt=None) -> dict:
        with self.lock, self.database.session() as session:
            repository = ProcessingRepository(session)
            source = repository.source(source_id)
            if source is None:
                raise ContentError(404, "Source not found.")
            if source.deleted_at is not None:
                raise ContentError(409, "Restore the Source before processing it.")
            ContentService.require_version(source, expected_version)
            require_source_input(source, self.registry.settings.ai_max_input_chars)
            snapshot = source_snapshot(source)
            run = ProcessingRun(
                source_id=source.id, source_version=source.version,
                source_snapshot=snapshot, input_hash=input_hash(snapshot),
                profile_id=resolved.profile_id, protocol=resolved.profile.protocol,
                model=resolved.profile.model, config_fingerprint=resolved.fingerprint,
                prompt_version=PROMPT_VERSION, prompt_hash=PROMPT_HASH,
                output_schema_version=OUTPUT_SCHEMA_VERSION,
                source_snapshots=[snapshot], prompt_snapshot=prompt,
                generation_settings={key: getattr(resolved.profile, key) for key in
                    ("max_output_tokens", "timeout_seconds") if hasattr(resolved.profile, key)},
            )
            if prompt:
                run.prompt_version = str(prompt["version"])
                import hashlib
                run.prompt_hash = hashlib.sha256(prompt["system_prompt"].encode("utf-8")).hexdigest()
                run.output_schema_version = prompt["output_schema_version"]
            session.add(run)
            session.commit()
            return run_dict(run, source)

    def _ready(self, run_id: str, result: dict, proposal: dict, usage: dict | None, finish_reason=None) -> dict:
        with self.lock, self.database.session() as session:
            repository = ProcessingRepository(session)
            run = self._require_run(repository, run_id)
            run.status, run.result, run.proposal, run.usage = "ready", result, proposal, usage
            run.finished_at = utcnow()
            run.finish_reason = finish_reason
            session.commit()
            return run_dict(run, repository.source(run.source_id))

    def _fail(self, run_id: str, code: str, stage=None, usage=None, finish_reason=None) -> None:
        with self.lock, self.database.session() as session:
            run = self._require_run(ProcessingRepository(session), run_id)
            run.status, run.error_code, run.finished_at = "failed", code, utcnow()
            run.failure_stage, run.usage, run.finish_reason = stage, usage, finish_reason
            session.commit()

    @staticmethod
    def _require_run(repository: ProcessingRepository, run_id: str) -> ProcessingRun:
        run = repository.run(run_id)
        if run is None:
            raise ContentError(404, "Processing run not found.")
        return run

    def list_runs(self, source_id: str | None = None, status: str | None = None,
                  profile_id: str | None = None, offset: int = 0, limit: int = 20, summary_only: bool = False) -> dict:
        try:
            with self.lock, self.database.session() as session:
                repository = ProcessingRepository(session)
                if summary_only:
                    items, total = repository.summary_page(source_id=source_id, status=status,
                        profile_id=profile_id, offset=offset, limit=limit)
                    return {"items": items, "total": total, "offset": offset, "limit": limit}
                records, total = repository.page(source_id=source_id, status=status,
                                                  profile_id=profile_id, offset=offset, limit=limit)
                return {"items": [run_dict(run, repository.source(run.source_id), detail=False)
                                  for run in records],
                        "total": total, "offset": offset, "limit": limit}
        except (SQLAlchemyError, RuntimeError):
            raise ProcessingFailure(503, "database_unavailable") from None

    def get_run(self, run_id: str) -> dict:
        try:
            with self.lock, self.database.session() as session:
                repository = ProcessingRepository(session)
                run = self._require_run(repository, run_id)
                return run_dict(run, repository.source(run.source_id))
        except (SQLAlchemyError, RuntimeError):
            raise ProcessingFailure(503, "database_unavailable", run_id) from None

    def adopt(self, run_id: str, expected_version: int) -> dict:
        try:
            try:
                return self._adopt(run_id, expected_version)
            except StaleDataError:
                # A competitor may have adopted while this transaction rolled
                # back both its prospective note and run update.
                current = self.get_run(run_id)
                if current["status"] == "adopted":
                    return self._adopt(run_id, expected_version)
                raise ContentError(409, "The processing run changed; reload its current version.") from None
        except (SQLAlchemyError, RuntimeError):
            raise ProcessingFailure(503, "database_unavailable", run_id) from None

    def _adopt(self, run_id: str, expected_version: int) -> dict:
        with self.lock, self.database.session() as session:
            repository = ProcessingRepository(session)
            run = self._require_run(repository, run_id)
            content = ContentService(session)
            source = repository.source(run.source_id)
            if run.status == "adopted":
                note = content.knowledge(run.adopted_knowledge_id, include_deleted=True)
                return {"run": run_dict(run, source), "knowledge": content.knowledge_dict(note),
                        "already_adopted": True}
            ContentService.require_version(run, expected_version)
            if run.status != "ready":
                raise ContentError(409, "Only a ready processing run can be adopted.")
            if run_dict(run, source, detail=False)["source_stale"]:
                raise ContentError(409, "The Source changed; generate a new draft before adoption.")
            note = content.create_knowledge(dict(run.proposal))
            run.status, run.adopted_knowledge_id = "adopted", note["id"]
            session.commit()
            return {"run": run_dict(run, source), "knowledge": note, "already_adopted": False}

    def recover_interrupted(self) -> None:
        """Run once after schema validation, before accepting new requests."""
        with self.lock, self.database.session() as session:
            for run in ProcessingRepository(session).running():
                run.status, run.error_code, run.finished_at = "interrupted", "interrupted", utcnow()
            session.commit()
        self.templates.ensure_builtins()
        self.batches.recover_interrupted()

    async def close(self) -> None:
        """Drain in-flight calls before the app disposes its shared database."""
        self._closing = True
        await self.batches.close()
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks)),
                                 return_exceptions=True)

    def request_stop(self) -> None:
        """Thread-safe intent flags: stop new calls before HTTP graceful drain."""
        self._closing = True
        self.batches._closing = True
