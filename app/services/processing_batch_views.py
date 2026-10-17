"""Paged batch metadata; polling never hydrates prompts, bodies or prior model outputs."""

from sqlalchemy import func, select, true

from app.models import ProcessingBatch, ProcessingBatchItem, ProcessingRun, Source
from app.services.content import ContentError
from app.services.processing_batch_records import ITEM_STATES


def summaries(session, *, identifier=None, status=None, offset=0, limit=20):
    batch = ProcessingBatch
    where = []
    if identifier is not None:
        where.append(batch.id == identifier)
    if status is not None:
        where.append(batch.status == status)
    columns = [getattr(batch, key) for key in ("id", "version", "client_request_id", "mode", "status",
        "profile_id", "model", "error_code", "created_at", "updated_at", "finished_at")]
    columns += [func.json_extract(batch.prompt_snapshot, "$.id").label("prompt_template_id"),
                func.json_extract(batch.prompt_snapshot, "$.version").label("prompt_template_version"),
                func.json_array_length(batch.source_snapshots).label("source_count")]
    total = session.scalar(select(func.count()).select_from(batch).where(*where)) or 0
    rows = session.execute(select(*columns).where(*where).order_by(
        batch.created_at.desc(), batch.id.desc()).offset(offset).limit(limit)).mappings()
    items = [dict(row) for row in rows]
    counts = {row["id"]: {state: 0 for state in ITEM_STATES} for row in items}
    if items:
        grouped = session.execute(select(ProcessingBatchItem.batch_id, ProcessingBatchItem.status, func.count())
            .where(ProcessingBatchItem.batch_id.in_(counts)).group_by(ProcessingBatchItem.batch_id, ProcessingBatchItem.status))
        for batch_id, state, count in grouped:
            counts[batch_id][state] = count
    for row in items:
        row.update(counts=counts[row["id"]], item_count=sum(counts[row["id"]].values()))
    if identifier is not None:
        if not items:
            raise ContentError(404, "Processing batch not found.")
        return items[0]
    return {"items": items, "total": int(total), "offset": offset, "limit": limit}


def item_page(session, identifier, *, offset=0, limit=20):
    # Snapshot metadata is extracted in SQLite; source content is not deserialized.
    exists = session.scalar(select(ProcessingBatch.id).where(ProcessingBatch.id == identifier))
    if exists is None:
        raise ContentError(404, "Processing batch not found.")
    snapshots = func.json_each(ProcessingBatch.source_snapshots).table_valued("value").alias("batch_sources")
    rows = session.execute(select(func.json_extract(snapshots.c.value, "$.id"),
        func.json_extract(snapshots.c.value, "$.version"), func.json_extract(snapshots.c.value, "$.title"))
        .select_from(ProcessingBatch).join(snapshots, onclause=true()).where(ProcessingBatch.id == identifier))
    versions = {source_id: {"id": source_id, "version": version, "title": title} for source_id, version, title in rows}
    current = {row.id: row for row in session.execute(select(Source.id, Source.version, Source.deleted_at)
                                                    .where(Source.id.in_(versions)))}
    total = session.scalar(select(func.count()).select_from(ProcessingBatchItem).where(ProcessingBatchItem.batch_id == identifier)) or 0
    fields = ("id", "position", "status", "source_ids", "run_id", "attempts", "error_code")
    records = session.execute(select(*(getattr(ProcessingBatchItem, key) for key in fields))
        .where(ProcessingBatchItem.batch_id == identifier).order_by(ProcessingBatchItem.position)
        .offset(offset).limit(limit)).mappings()
    items = []
    for item in records:
        row = dict(item)
        row["sources"] = [versions[source_id] for source_id in row["source_ids"] if source_id in versions]
        row["source_stale"] = any(source_id not in current or current[source_id].deleted_at is not None
            or current[source_id].version != versions[source_id]["version"] for source_id in row["source_ids"])
        items.append(row)
    return {"items": items, "total": int(total), "offset": offset, "limit": limit}


def attempt_page(session, identifier, item_id, *, offset=0, limit=20):
    total = session.scalar(select(func.json_array_length(ProcessingBatchItem.run_ids)).where(
        ProcessingBatchItem.id == item_id, ProcessingBatchItem.batch_id == identifier))
    if total is None:
        raise ContentError(404, "Batch item not found.")
    attempts = func.json_each(ProcessingBatchItem.run_ids).table_valued("key", "value").alias("attempt_ids")
    records = session.execute(select(*(getattr(ProcessingRun, key) for key in (
        "id", "version", "status", "error_code", "failure_stage", "finish_reason", "usage", "created_at", "finished_at")))
        .select_from(ProcessingBatchItem).join(attempts, true())
        .join(ProcessingRun, ProcessingRun.id == attempts.c.value)
        .where(ProcessingBatchItem.id == item_id, ProcessingBatchItem.batch_id == identifier)
        .order_by(attempts.c.key.desc()).offset(offset).limit(limit)).mappings()
    return {"items": [dict(row) for row in records], "total": int(total), "offset": offset, "limit": limit}
