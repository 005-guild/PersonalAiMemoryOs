"""Import identity and legacy-URL queries without transaction ownership."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Source, SourceOrigin


class ImportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def origin(self, resource_type: str, external_id: str) -> SourceOrigin | None:
        return self.session.scalar(select(SourceOrigin).where(
            SourceOrigin.provider == "zhihu",
            SourceOrigin.resource_type == resource_type,
            SourceOrigin.external_id == external_id,
        ))

    def source(self, source_id: str) -> Source | None:
        # Tombstones still own their external identity.
        return self.session.get(Source, source_id)

    def unmapped_urls(self, resource_type: str, external_id: str) -> list[tuple[str, str]]:
        """Narrow URL candidates; callers still validate their complete identity."""
        segment = {"answer": "answer", "article": "p", "pin": "pin"}[resource_type]
        fragment = f"/{segment}/{external_id}"
        return list(self.session.execute(
            select(Source.id, Source.url).outerjoin(
                SourceOrigin, SourceOrigin.source_id == Source.id
            ).where(SourceOrigin.source_id.is_(None), Source.url.is_not(None),
                    Source.url.contains(fragment, autoescape=True))
            .order_by(Source.id)
        ).tuples())

    def add_origin(self, *, source_id: str, resource_type: str, external_id: str) -> None:
        self.session.add(SourceOrigin(
            source_id=source_id, provider="zhihu", resource_type=resource_type,
            external_id=external_id,
        ))
