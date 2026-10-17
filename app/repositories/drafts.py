"""Bounded draft projections; full model results and source bodies stay in detail APIs."""

from sqlalchemy import case, func, or_, select

from app.models import ProcessingRun


class DraftRepository:
    def __init__(self, session):
        self.session = session

    def page(self, *, q="", state="all", profile_id=None, source_id=None,
             prompt_template_id=None, offset=0, limit=20):
        run = ProcessingRun
        title = func.coalesce(func.json_extract(run.proposal, "$.title"), "")
        where = [run.status.in_(["ready", "adopted"])]
        if state != "all":
            where.append(run.status == state)
        if q:
            where.append(title.contains(q, autoescape=True))
        if profile_id is not None:
            where.append(run.profile_id == profile_id)
        if source_id is not None:
            sources = func.json_each(run.source_snapshots).table_valued("value").alias("draft_sources")
            linked = select(1).select_from(sources).where(func.json_extract(sources.c.value, "$.id") == source_id).exists()
            where.append(or_(run.source_id == source_id, linked))
        if prompt_template_id is not None:
            where.append(func.json_extract(run.prompt_snapshot, "$.id") == prompt_template_id)
        total = self.session.scalar(select(func.count()).select_from(run).where(*where)) or 0
        columns = [getattr(run, key) for key in ("id", "version", "status", "source_id", "profile_id",
            "model", "created_at", "updated_at", "finished_at", "adopted_knowledge_id", "output_schema_version")]
        columns += [title.label("title"), func.substr(func.coalesce(func.json_extract(run.proposal, "$.summary"), ""), 1, 240).label("excerpt"),
                    case((func.json_array_length(run.source_snapshots) > 0,
                          func.json_array_length(run.source_snapshots)), else_=1).label("source_count")]
        for field in ("id", "version", "name", "purpose"):
            columns.append(func.json_extract(run.prompt_snapshot, "$." + field).label("prompt_template_" + field))
        rows = self.session.execute(select(*columns).where(*where).order_by(
            run.created_at.desc(), run.id.desc()).offset(offset).limit(limit)).mappings()
        return {"items": [dict(row) for row in rows], "total": int(total), "offset": offset, "limit": limit}
