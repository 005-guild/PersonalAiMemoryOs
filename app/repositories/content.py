"""Queries for content records; transactions belong to the calling service."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Knowledge, KnowledgeSource, Source, SyncState


class ContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def source(self, source_id: str) -> Source | None:
        return self.session.get(Source, source_id)

    def knowledge(self, knowledge_id: str) -> Knowledge | None:
        return self.session.get(Knowledge, knowledge_id)

    def sync_state(self, knowledge_id: str) -> SyncState | None:
        return self.session.get(SyncState, knowledge_id)

    def has_active_knowledge(self, source_id: str) -> bool:
        return self.session.scalar(
            select(Knowledge.id).where(
                self.source_predicate(source_id), Knowledge.deleted_at.is_(None)
            ).limit(1)
        ) is not None

    @staticmethod
    def source_predicate(source_id):
        return or_(Knowledge.source_id == source_id, select(KnowledgeSource.knowledge_id).where(
            KnowledgeSource.knowledge_id == Knowledge.id, KnowledgeSource.source_id == source_id).exists())

    def page(self, model, *, include_deleted: bool, offset: int, limit: int,
             source_id: str | None = None) -> tuple[list, int]:
        predicates = [] if include_deleted else [model.deleted_at.is_(None)]
        if source_id is not None and model is Knowledge:
            predicates.append(self.source_predicate(source_id))
        total = self.session.scalar(select(func.count()).select_from(model).where(*predicates))
        records = self.session.scalars(
            select(model).where(*predicates).order_by(model.created_at, model.id)
            .offset(offset).limit(limit)
        ).all()
        return list(records), total or 0
