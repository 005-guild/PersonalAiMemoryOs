"""Public batch projections never include authentication values or private clients."""

from sqlalchemy import select

from app.models import ProcessingBatchItem, Source

ITEM_STATES = ("pending", "running", "ready", "failed", "interrupted", "cancelled")


def batch_dict(session, batch, *, detail=True):
    items = list(session.scalars(select(ProcessingBatchItem).where(ProcessingBatchItem.batch_id == batch.id)
                                 .order_by(ProcessingBatchItem.position)))
    result = {key: getattr(batch, key) for key in (
        "id", "version", "client_request_id", "mode", "status", "profile_id", "model", "error_code",
        "created_at", "updated_at", "finished_at")}
    result.update(prompt_template_id=batch.prompt_snapshot["id"],
        prompt_template_version=batch.prompt_snapshot["version"], source_count=len(batch.source_snapshots),
        item_count=len(items), counts={state: sum(item.status == state for item in items) for state in ITEM_STATES})
    if detail:
        current = {source["id"]: session.get(Source, source["id"]) for source in batch.source_snapshots}
        stale = {source["id"] for source in batch.source_snapshots if current[source["id"]] is None
            or current[source["id"]].deleted_at is not None or current[source["id"]].version != source["version"]}
        result.update(source_snapshots=batch.source_snapshots, prompt_snapshot=batch.prompt_snapshot,
                      profile_snapshot=batch.profile_snapshot, generation_settings=batch.generation_settings, items=[{
            **{key: getattr(item, key) for key in ("id", "position", "status", "source_ids", "run_id", "run_ids", "attempts", "error_code")},
            "source_stale": bool(set(item.source_ids) & stale)} for item in items])
    return result
