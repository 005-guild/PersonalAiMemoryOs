"""Read-only workbench views composed from bounded database projections."""

from sqlalchemy.orm import Session

from app.repositories.ui import RecordState, SortOrder, SourceGroupSort, UIRepository


class UIService:
    def __init__(self, session: Session) -> None:
        self.repository = UIRepository(session)

    def overview(self) -> dict[str, int]:
        return self.repository.overview()

    def sources(self, *, q: str, state: RecordState, offset: int, limit: int) -> dict:
        items, total = self.repository.sources(q=q, state=state, offset=offset, limit=limit)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def source_groups(self, *, q: str, state: RecordState, offset: int, limit: int,
                      sort_by: SourceGroupSort = "updated_at", order: SortOrder = "desc") -> dict:
        items, total, total_sources = self.repository.source_groups(
            q=q, state=state, offset=offset, limit=limit, sort_by=sort_by, order=order,
        )
        return {"items": items, "total": total, "total_sources": total_sources,
                "offset": offset, "limit": limit}

    def source_group_items(self, *, title: str, state: RecordState, offset: int, limit: int) -> dict:
        items, total = self.repository.source_group_items(
            title=title, state=state, offset=offset, limit=limit,
        )
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def knowledge(self, *, q: str, state: RecordState, offset: int, limit: int,
                  source_id: str | None) -> dict:
        items, total = self.repository.knowledge(
            q=q, state=state, offset=offset, limit=limit, source_id=source_id,
        )
        for item in items:
            item["deleted"] = item["deleted_at"] is not None
        return {"items": items, "total": total, "offset": offset, "limit": limit}
