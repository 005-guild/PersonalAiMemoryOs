"""Generate durable drafts outside transactions, then adopt them atomically."""

import asyncio

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.agents.errors import AIError
from app.agents.generation_gate import GenerationGate
from app.agents.prompts import PROMPT_HASH, PROMPT_VERSION, build_prompts
from app.models import ProcessingRun, utcnow
from app.repositories.processing import ProcessingRepository
from app.services.content import ContentError, ContentService
from app.services.processing_output import OUTPUT_SCHEMA_VERSION, render_proposal, validate_output
from app.services.processing_records import input_hash, run_dict, source_snapshot


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

    async def generate(self, source_id: str, expected_source_version: int,
                       profile_id: str | None = None) -> dict:
        if self._closing:
            raise ProcessingFailure(503, "processing_unavailable")
        resolved = self.registry.resolve(profile_id)
        if not self._gate.acquire(blocking=False):
            raise ProcessingFailure(429, "processing_busy")
        task = asyncio.create_task(self._generate(source_id, expected_source_version, resolved))
        self._tasks.add(task)
        task.add_done_callback(self._finished_task)
        # A disconnected caller must not leave an unqueryable half-finished run.
        return await asyncio.shield(task)

    def _finished_task(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve a detached caller's failure without logging raw data.

    async def _generate(self, source_id: str, expected_source_version: int, resolved) -> dict:
        run_id = None
        try:
            run = await asyncio.to_thread(self._begin, source_id, expected_source_version, resolved)
            run_id = run["id"]
            try:
                system_prompt, user_prompt = build_prompts(run["source_snapshot"])
                reply = await self.model_client.generate(resolved, system_prompt, user_prompt)
                result = validate_output(reply.text, run["source_snapshot"])
                proposal = render_proposal(result, run["source_snapshot"])
            except AIError as error:
                await asyncio.to_thread(self._fail, run_id, error.code)
                raise ProcessingFailure(error.status_code, error.code, run_id) from None
            except Exception:
                await asyncio.to_thread(self._fail, run_id, "processing_failed")
                raise ProcessingFailure(502, "processing_failed", run_id) from None
            return await asyncio.to_thread(self._ready, run_id, result, proposal, reply.usage)
        except (SQLAlchemyError, RuntimeError):
            raise ProcessingFailure(503, "database_unavailable", run_id) from None
        finally:
            self._gate.release()

    def _begin(self, source_id: str, expected_version: int, resolved) -> dict:
        with self.lock, self.database.session() as session:
            repository = ProcessingRepository(session)
            source = repository.source(source_id)
            if source is None:
                raise ContentError(404, "Source not found.")
            if source.deleted_at is not None:
                raise ContentError(409, "Restore the Source before processing it.")
            ContentService.require_version(source, expected_version)
            if not source.content.strip():
                raise ContentError(422, "Source content must not be empty.")
            if len(source.content) > self.registry.settings.ai_max_input_chars:
                raise ContentError(422, "Source content exceeds the configured AI input limit.")
            snapshot = source_snapshot(source)
            run = ProcessingRun(
                source_id=source.id, source_version=source.version,
                source_snapshot=snapshot, input_hash=input_hash(snapshot),
                profile_id=resolved.profile_id, protocol=resolved.profile.protocol,
                model=resolved.profile.model, config_fingerprint=resolved.fingerprint,
                prompt_version=PROMPT_VERSION, prompt_hash=PROMPT_HASH,
                output_schema_version=OUTPUT_SCHEMA_VERSION,
            )
            session.add(run)
            session.commit()
            return run_dict(run, source)

    def _ready(self, run_id: str, result: dict, proposal: dict, usage: dict | None) -> dict:
        with self.lock, self.database.session() as session:
            repository = ProcessingRepository(session)
            run = self._require_run(repository, run_id)
            run.status, run.result, run.proposal, run.usage = "ready", result, proposal, usage
            run.finished_at = utcnow()
            session.commit()
            return run_dict(run, repository.source(run.source_id))

    def _fail(self, run_id: str, code: str) -> None:
        with self.lock, self.database.session() as session:
            run = self._require_run(ProcessingRepository(session), run_id)
            run.status, run.error_code, run.finished_at = "failed", code, utcnow()
            session.commit()

    @staticmethod
    def _require_run(repository: ProcessingRepository, run_id: str) -> ProcessingRun:
        run = repository.run(run_id)
        if run is None:
            raise ContentError(404, "Processing run not found.")
        return run

    def list_runs(self, source_id: str | None = None, status: str | None = None,
                  profile_id: str | None = None, offset: int = 0, limit: int = 20) -> dict:
        try:
            with self.lock, self.database.session() as session:
                repository = ProcessingRepository(session)
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

    async def close(self) -> None:
        """Drain in-flight calls before the app disposes its shared database."""
        self._closing = True
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks)),
                                 return_exceptions=True)
