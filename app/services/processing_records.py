"""Stable snapshots and response projection for saved AI drafts."""

import hashlib
import json

from app.models import ProcessingRun, Source

SUMMARY_FIELDS = (
    "id", "version", "source_id", "source_version", "profile_id", "protocol", "model", "status",
    "error_code", "adopted_knowledge_id", "created_at", "updated_at", "started_at", "finished_at",
)
DETAIL_FIELDS = (
    "source_snapshot", "input_hash", "config_fingerprint", "prompt_version", "prompt_hash",
    "output_schema_version", "result", "proposal", "usage", "source_snapshots", "prompt_snapshot",
    "generation_settings", "finish_reason", "failure_stage",
)


def source_snapshot(source: Source) -> dict:
    return {field: getattr(source, field) for field in (
        "id", "source_type", "title", "author", "url", "content", "version",
    )}


def input_hash(snapshot: dict) -> str:
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_dict(run: ProcessingRun, source: Source | None, *, detail: bool = True, sources=None) -> dict:
    fields = SUMMARY_FIELDS + (DETAIL_FIELDS if detail else ())
    data = {field: getattr(run, field) for field in fields}
    data["source_count"] = len(run.source_snapshots) if run.source_snapshots else 1
    data["source_ids"] = [row["id"] for row in run.source_snapshots] if run.source_snapshots else [run.source_id]
    data["source_stale"] = source is None or source.deleted_at is not None or source.version != run.source_version
    if run.source_snapshots:
        from sqlalchemy.orm import object_session
        session = object_session(run)
        lookup = sources or {snapshot["id"]: session.get(Source, snapshot["id"]) for snapshot in run.source_snapshots}
        data["source_stale"] = any(lookup.get(snapshot["id"]) is None
            or lookup[snapshot["id"]].deleted_at is not None
            or lookup[snapshot["id"]].version != snapshot["version"] for snapshot in run.source_snapshots)
    if detail:
        data["source_snapshots"] = run.source_snapshots or [run.source_snapshot]
    return data
