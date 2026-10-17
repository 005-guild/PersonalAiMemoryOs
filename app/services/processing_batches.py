"""User-authorized persistent batches, one call at a time with no implicit retries."""

import asyncio
from sqlalchemy.exc import SQLAlchemyError

from app.agents.configuration import AIProfile, ResolvedProfile
from app.agents.errors import AIError
from app.services.content import ContentError
from app.services.processing_batch_store import BatchStore
from app.services.processing_records import input_hash

CONTINUE_ERRORS = {"invalid_output", "invalid_evidence", "model_refused"}


class ProcessingBatchService:
    def __init__(self, owner):
        self.owner = owner
        self.store = BatchStore(owner)
        self._tasks = {}
        self._reschedule = set()
        self._operations = set()
        self._dispatch = asyncio.Lock()
        self._closing = False

    async def create(self, payload):
        return await self._owned(self._create(payload))

    async def _owned(self, operation):
        task = asyncio.create_task(operation)
        self._operations.add(task)
        def finished(result):
            self._operations.discard(result)
            if not result.cancelled():
                result.exception()
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def _create(self, payload):
        if self._closing or self.owner._closing:
            raise ContentError(503, "Processing is stopping.")
        await asyncio.to_thread(self.owner.templates.ensure_builtins)
        result, created = await asyncio.to_thread(self.store.create, payload)
        if created:
            self._schedule(result["id"])
        return result

    def _schedule(self, identifier):
        if identifier in self._tasks:
            self._reschedule.add(identifier)
            return
        task = asyncio.create_task(self._run(identifier))
        self._tasks[identifier] = task
        def finished(result):
            self._tasks.pop(identifier, None)
            if not result.cancelled():
                result.exception()
            if identifier in self._reschedule:
                self._reschedule.discard(identifier)
                if not self._closing and not self.owner._closing:
                    self._schedule(identifier)
        task.add_done_callback(finished)

    def _resolved(self, identifier):
        profile_id, snapshot = self.store.profile(identifier)
        # A persisted snapshot is not permission to bypass a configuration the
        # user subsequently disabled, removed, or pointed at a different service.
        active = self.owner.registry.resolve(profile_id)
        profile = AIProfile.model_validate(snapshot)
        effective = active.profile.model_copy(update={key: snapshot[key] for key in ("max_output_tokens", "timeout_seconds")})
        if effective.model_dump() != profile.model_dump():
            raise AIError(409, "batch_profile_changed")
        return ResolvedProfile(profile_id, profile, active.api_key, input_hash(profile.model_dump()))

    async def action(self, identifier, expected_version, action):
        return await self._owned(self._action(identifier, expected_version, action))

    async def _action(self, identifier, expected_version, action):
        if action != "cancel":
            if self._closing or self.owner._closing:
                raise ContentError(503, "Processing is stopping.")
            await asyncio.to_thread(self._resolved, identifier)
        result = await asyncio.to_thread(self.store.action, identifier, expected_version, action)
        if action != "cancel":
            self._schedule(identifier)
        return result

    async def _run(self, identifier):
        async with self._dispatch:
            while True:
                if self._closing or self.owner._closing:
                    await asyncio.to_thread(self.store.pause, identifier, "shutdown")
                    return
                current = await asyncio.to_thread(self.store.get, identifier)
                if current["status"] in {"paused", "cancelled", "completed", "cancelling"}:
                    return
                if not self.owner._gate.acquire(blocking=False):
                    await asyncio.sleep(.05)
                    continue
                item = None
                try:
                    resolved = await asyncio.to_thread(self._resolved, identifier)
                    item = await asyncio.to_thread(self.store.begin_item, identifier, resolved)
                    if item is None:
                        return
                    item_id, run = item
                    if run is None:
                        continue
                    await self.owner.execute_run(run, resolved)
                    await asyncio.to_thread(self.store.finish_item, identifier, item_id)
                except Exception as error:
                    code = getattr(error, "code", "database_unavailable" if isinstance(error, (RuntimeError, SQLAlchemyError)) else "processing_failed")
                    pause = code not in CONTINUE_ERRORS
                    if item is not None:
                        await asyncio.to_thread(self.store.finish_item, identifier, item[0], error=code, pause=pause)
                    else:
                        await asyncio.to_thread(self.store.pause, identifier, code)
                        return
                    if pause:
                        return
                finally:
                    self.owner._gate.release()

    def recover_interrupted(self):
        self.store.recover()

    def get(self, identifier, *, summary_only=False):
        return self.store.get(identifier, summary_only=summary_only)

    def list(self, **kwargs):
        return self.store.list(**kwargs)

    async def close(self):
        self._closing = True
        if self._operations:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._operations)), return_exceptions=True)
        if self._tasks:
            await asyncio.gather(*(asyncio.shield(task) for task in tuple(self._tasks.values())), return_exceptions=True)
