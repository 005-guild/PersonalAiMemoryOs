"""Short, locked transactions for snapshots, call intent and explicit batch controls."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agents.prompts import build_template_prompts
from app.models import ProcessingBatch, ProcessingBatchItem, ProcessingRun, Source, utcnow
from app.services.content import ContentError, ContentService
from app.services.processing_batch_records import batch_dict
from app.services.processing_records import input_hash, run_dict, source_snapshot
from app.services.prompt_templates import snapshot_template
from app.services.processing_limits import require_source_input


class BatchStore:
    def __init__(self, owner):
        self.owner, self.database, self.lock = owner, owner.database, owner.lock

    @staticmethod
    def require(session, identifier):
        record = session.get(ProcessingBatch, identifier)
        if record is None:
            raise ContentError(404, "Processing batch not found.")
        return record

    def create(self, payload):
        try:
            return self._create(payload)
        except IntegrityError:
            # The unique client token is the cross-process idempotency authority.
            with self.lock, self.database.session() as session:
                batch = session.scalar(select(ProcessingBatch).where(ProcessingBatch.client_request_id == payload["client_request_id"]))
                if batch is None:
                    raise
                if batch.request_hash != input_hash(payload):
                    raise ContentError(409, "This client_request_id belongs to a different batch request.") from None
                return batch_dict(session, batch), False

    def _create(self, payload):
        request_hash = input_hash(payload)
        with self.lock, self.database.session() as session:
            existing = session.scalar(select(ProcessingBatch).where(ProcessingBatch.client_request_id == payload["client_request_id"]))
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise ContentError(409, "This client_request_id belongs to a different batch request.")
                return batch_dict(session, existing), False
            resolved = self.owner.registry.resolve(payload.get("profile_id"))
            prompt = snapshot_template(session, payload.get("prompt_template_id"), payload.get("prompt_template_version"))
            snapshots = []
            for selected in payload["sources"]:
                source = ContentService(session).source(selected["source_id"], include_deleted=True)
                if source.deleted_at is not None:
                    raise ContentError(409, "Restore selected Sources before processing them.")
                ContentService.require_version(source, selected["expected_version"])
                require_source_input(source, self.owner.registry.settings.ai_max_input_chars)
                snapshots.append(source_snapshot(source))
            if payload["mode"] == "merged":
                total_chars = sum(len(source["content"]) for source in snapshots)
                if total_chars > self.owner.registry.settings.ai_max_input_chars:
                    raise ContentError(422, f"合并资料共 {total_chars} 字符，超过当前输入上限 "
                        f"{self.owner.registry.settings.ai_max_input_chars}；请减少所选资料或调整配置后重启。")
                if prompt["output_schema_version"] != 2:
                    raise ContentError(422, "Merged processing requires a version 2 output template.")
            settings = payload["generation_settings"]
            profile = resolved.profile.model_copy(update=settings)
            prompt["system_prompt"] = build_template_prompts(prompt, snapshots)[0]
            batch = ProcessingBatch(client_request_id=payload["client_request_id"], request_hash=request_hash,
                mode=payload["mode"], profile_id=resolved.profile_id, model=profile.model,
                profile_snapshot=profile.model_dump(), prompt_snapshot=prompt,
                generation_settings=settings, source_snapshots=snapshots)
            session.add(batch)
            session.flush()
            groups = [[source["id"]] for source in snapshots] if payload["mode"] == "individual" else [[source["id"] for source in snapshots]]
            for position, ids in enumerate(groups):
                session.add(ProcessingBatchItem(batch_id=batch.id, position=position, source_ids=ids))
            session.commit()
            return batch_dict(session, batch), True

    def get(self, identifier, *, summary_only=False):
        with self.lock, self.database.session() as session:
            if summary_only:
                from app.services.processing_batch_views import summaries
                return summaries(session, identifier=identifier)
            return batch_dict(session, self.require(session, identifier))

    def list(self, *, status=None, offset=0, limit=20):
        with self.lock, self.database.session() as session:
            from app.services.processing_batch_views import summaries
            return summaries(session, status=status, offset=offset, limit=limit)

    def items(self, identifier, *, offset=0, limit=20):
        from app.services.processing_batch_views import item_page
        with self.lock, self.database.session() as session:
            return item_page(session, identifier, offset=offset, limit=limit)

    def attempts(self, identifier, item_id, *, offset=0, limit=20):
        from app.services.processing_batch_views import attempt_page
        with self.lock, self.database.session() as session:
            return attempt_page(session, identifier, item_id, offset=offset, limit=limit)

    def action(self, identifier, expected_version, action):
        with self.lock, self.database.session() as session:
            batch = self.require(session, identifier)
            ContentService.require_version(batch, expected_version)
            items = list(session.scalars(select(ProcessingBatchItem).where(ProcessingBatchItem.batch_id == identifier)))
            if action == "cancel":
                if batch.status in {"completed", "cancelled"}:
                    return batch_dict(session, batch)
                batch.cancel_requested = True
                running = any(item.status == "running" for item in items)
                for item in items:
                    if item.status == "pending":
                        item.status = "cancelled"
                batch.status = "cancelling" if running else "cancelled"
                if not running:
                    batch.finished_at = utcnow()
            else:
                if batch.status not in {"paused", "completed"}:
                    raise ContentError(409, "Only a paused/completed batch can be explicitly resumed.")
                if action == "retry-failed":
                    for item in items:
                        if item.status in {"failed", "interrupted"}:
                            item.status, item.error_code = "pending", None
                if not any(item.status == "pending" for item in items):
                    raise ContentError(409, "There are no pending items for this operation.")
                batch.status, batch.error_code, batch.finished_at, batch.cancel_requested = "pending", None, None, False
            batch.updated_at = utcnow()
            session.commit()
            return batch_dict(session, batch)

    def profile(self, identifier):
        with self.lock, self.database.session() as session:
            batch = self.require(session, identifier)
            return batch.profile_id, dict(batch.profile_snapshot)

    def begin_item(self, identifier, resolved):
        with self.lock, self.database.session() as session:
            batch = self.require(session, identifier)
            if self.owner._closing or self.owner.batches._closing:
                if batch.status not in {"cancelled", "completed"}:
                    batch.status, batch.error_code, batch.updated_at = "paused", "shutdown", utcnow()
                    session.commit()
                return None
            if batch.cancel_requested or batch.status in {"paused", "cancelled", "completed"}:
                return None
            item = session.scalar(select(ProcessingBatchItem).where(ProcessingBatchItem.batch_id == identifier,
                ProcessingBatchItem.status == "pending").order_by(ProcessingBatchItem.position).limit(1))
            if item is None:
                batch.status, batch.finished_at = "completed", utcnow()
                session.commit()
                return None
            snapshots = [source for source in batch.source_snapshots if source["id"] in item.source_ids]
            current = {source["id"]: session.get(Source, source["id"]) for source in snapshots}
            if any(current[source["id"]] is None or current[source["id"]].deleted_at is not None
                   or current[source["id"]].version != source["version"] for source in snapshots):
                # Check after waiting for the global slot, immediately before
                # committing a call intent. Stale queued material never incurs a call.
                item.status, item.error_code = "failed", "source_stale"
                batch.status, batch.updated_at = "running", utcnow()
                session.commit()
                return item.id, None
            first, prompt = snapshots[0], batch.prompt_snapshot
            system = prompt["system_prompt"]
            run = ProcessingRun(source_id=first["id"], source_version=first["version"], source_snapshot=first,
                source_snapshots=snapshots, input_hash=input_hash({"sources": snapshots}), profile_id=batch.profile_id,
                protocol=resolved.profile.protocol, model=resolved.profile.model, config_fingerprint=resolved.fingerprint,
                prompt_version=str(prompt["version"]), prompt_hash=hashlib.sha256(system.encode("utf-8")).hexdigest(),
                output_schema_version=prompt["output_schema_version"], prompt_snapshot=prompt,
                generation_settings=batch.generation_settings)
            session.add(run)
            session.flush()
            item.status, item.run_id, item.attempts = "running", run.id, item.attempts + 1
            item.run_ids = [*item.run_ids, run.id]
            batch.status, batch.updated_at = "running", utcnow()
            session.commit()
            return item.id, run_dict(run, session.get(Source, first["id"]))

    def finish_item(self, identifier, item_id, *, error=None, pause=False):
        with self.lock, self.database.session() as session:
            batch = self.require(session, identifier)
            item = session.get(ProcessingBatchItem, item_id)
            item.status, item.error_code = ("failed" if error else "ready"), error
            run = session.get(ProcessingRun, item.run_id) if item.run_id else None
            if error and run is not None and run.status == "running":
                # A paid reply could not be published. Preserve uncertainty and
                # require a new explicit retry rather than leaving a fake active call.
                run.status, run.error_code, run.failure_stage = "interrupted", error, "persistence"
                run.finished_at = utcnow()
                item.status = "interrupted"
            if batch.cancel_requested:
                batch.status, batch.finished_at = "cancelled", utcnow()
                for pending in session.scalars(select(ProcessingBatchItem).where(
                        ProcessingBatchItem.batch_id == identifier, ProcessingBatchItem.status == "pending")):
                    pending.status = "cancelled"
            elif pause:
                batch.status, batch.error_code = "paused", error
            batch.updated_at = utcnow()
            session.commit()

    def pause(self, identifier, code):
        with self.lock, self.database.session() as session:
            batch = self.require(session, identifier)
            if batch.status not in {"cancelled", "completed", "cancelling"}:
                batch.status, batch.error_code, batch.updated_at = "paused", code, utcnow()
                session.commit()

    def recover(self):
        with self.lock, self.database.session() as session:
            for batch in session.scalars(select(ProcessingBatch).where(
                    ProcessingBatch.status.in_(["pending", "running", "cancelling"]))):
                items = list(session.scalars(select(ProcessingBatchItem).where(ProcessingBatchItem.batch_id == batch.id)))
                for item in items:
                    if item.status == "running":
                        run = session.get(ProcessingRun, item.run_id) if item.run_id else None
                        if run is not None and run.status in {"ready", "adopted"}:
                            item.status, item.error_code = "ready", None
                        elif run is not None and run.status == "failed":
                            item.status, item.error_code = "failed", run.error_code
                        else:
                            item.status, item.error_code = "interrupted", "interrupted"
                    elif batch.cancel_requested and item.status == "pending":
                        item.status = "cancelled"
                batch.status = "cancelled" if batch.cancel_requested else "paused"
                batch.error_code, batch.updated_at = "interrupted", utcnow()
                if not batch.cancel_requested and all(item.status == "ready" for item in items):
                    batch.status, batch.error_code, batch.finished_at = "completed", None, utcnow()
            session.commit()
