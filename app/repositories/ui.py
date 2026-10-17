"""Small read projections for the workbench; large documents stay in detail APIs."""

from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Knowledge, ProcessingRun, Source, SyncConflict, SyncState

RecordState = Literal["active", "deleted", "all"]
SourceGroupSort = Literal["title", "source_count", "source_type", "updated_at"]
SortOrder = Literal["asc", "desc"]
EXCERPT_LENGTH = 240


class UIRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def overview(self) -> dict[str, int]:
        queries = {
            "active_sources": select(func.count()).select_from(Source).where(Source.deleted_at.is_(None)),
            "active_knowledge": select(func.count()).select_from(Knowledge).where(Knowledge.deleted_at.is_(None)),
            "ready_drafts": select(func.count()).select_from(ProcessingRun).where(ProcessingRun.status == "ready"),
            "open_conflicts": select(func.count()).select_from(SyncConflict).where(SyncConflict.status == "open"),
        }
        return {name: int(self.session.scalar(query) or 0) for name, query in queries.items()}

    @staticmethod
    def _filters(model, q: str, state: RecordState) -> list:
        predicates = []
        if state == "active":
            predicates.append(model.deleted_at.is_(None))
        elif state == "deleted":
            predicates.append(model.deleted_at.is_not(None))
        if q:
            # %, _ and the escape character are literal title characters.
            predicates.append(model.title.contains(q, autoescape=True))
        return predicates

    @staticmethod
    def _record_columns(model) -> tuple:
        return (model.id, model.title, model.version, model.created_at,
                model.updated_at, model.deleted_at)

    def sources(self, *, q: str, state: RecordState, offset: int, limit: int) -> tuple[list[dict], int]:
        predicates = self._filters(Source, q, state)
        return self._source_page(predicates, offset=offset, limit=limit,
                                 ordering=(Source.updated_at.desc(), Source.id.desc()))

    def source_group_items(self, *, title: str, state: RecordState,
                           offset: int, limit: int) -> tuple[list[dict], int]:
        predicates = [*self._filters(Source, "", state), Source.title == title]
        return self._source_page(predicates, offset=offset, limit=limit,
                                 ordering=(Source.updated_at.desc(), Source.id.asc()))

    def _source_page(self, predicates: list, *, offset: int, limit: int,
                     ordering: tuple) -> tuple[list[dict], int]:
        total = self.session.scalar(select(func.count()).select_from(Source).where(*predicates)) or 0
        rows = self.session.execute(
            select(*self._record_columns(Source), Source.source_type, Source.author, Source.url,
                   func.substr(Source.content, 1, EXCERPT_LENGTH).label("excerpt"))
            .where(*predicates).order_by(*ordering)
            .offset(offset).limit(limit)
        ).mappings().all()
        return [dict(row) for row in rows], int(total)

    def source_groups(self, *, q: str, state: RecordState,
                      offset: int, limit: int, sort_by: SourceGroupSort = "updated_at",
                      order: SortOrder = "desc") -> tuple[list[dict], int, int]:
        predicates = self._filters(Source, q, state)
        # Group the complete filtered set before LIMIT; a title never splits pages.
        grouped = select(
            Source.title, func.count().label("source_count"),
            func.sum(case((Source.deleted_at.is_(None), 1), else_=0)).label("active_count"),
            func.sum(case((Source.deleted_at.is_not(None), 1), else_=0)).label("deleted_count"),
            func.max(Source.updated_at).label("latest_updated_at"),
            # A scalar minimum preserves arbitrary type text, including commas.
            func.min(Source.source_type).label("source_type_sort_key"),
        ).where(*predicates).group_by(Source.title).subquery()
        total, total_sources = self.session.execute(select(
            func.count(), func.coalesce(func.sum(grouped.c.source_count), 0),
        ).select_from(grouped)).one()
        column = {"title": grouped.c.title, "source_count": grouped.c.source_count,
                  "source_type": grouped.c.source_type_sort_key,
                  "updated_at": grouped.c.latest_updated_at}[sort_by]
        primary = column.asc() if order == "asc" else column.desc()
        ordering = (primary,) if sort_by == "title" else (primary, grouped.c.title.asc())
        rows = self.session.execute(select(
            grouped.c.title, grouped.c.source_count, grouped.c.active_count,
            grouped.c.deleted_count, grouped.c.latest_updated_at,
        ).order_by(*ordering).offset(offset).limit(limit)).mappings().all()
        items = [dict(row, source_types=[]) for row in rows]
        if items:
            by_title = {item["title"]: item for item in items}
            # Only visible titles need type metadata; DISTINCT avoids source hydration.
            types = self.session.execute(select(Source.title, Source.source_type)
                .where(*predicates, Source.title.in_(by_title))
                .distinct().order_by(Source.title.asc(), Source.source_type.asc()))
            for title, source_type in types:
                by_title[title]["source_types"].append(source_type)
        return items, int(total), int(total_sources)

    def knowledge(self, *, q: str, state: RecordState, offset: int, limit: int,
                  source_id: str | None) -> tuple[list[dict], int]:
        predicates = self._filters(Knowledge, q, state)
        if source_id is not None:
            predicates.append(Knowledge.source_id == source_id)
        total = self.session.scalar(select(func.count()).select_from(Knowledge).where(*predicates)) or 0
        rows = self.session.execute(
            select(*self._record_columns(Knowledge), Knowledge.source_id,
                   func.substr(Knowledge.summary, 1, EXCERPT_LENGTH).label("summary"),
                   Knowledge.category, Knowledge.tags, Knowledge.concepts,
                   func.coalesce(SyncState.status, "pending").label("sync_status"), SyncState.path)
            .outerjoin(SyncState, SyncState.knowledge_id == Knowledge.id)
            .where(*predicates).order_by(Knowledge.updated_at.desc(), Knowledge.id.desc())
            .offset(offset).limit(limit)
        ).mappings().all()
        return [dict(row) for row in rows], int(total)
