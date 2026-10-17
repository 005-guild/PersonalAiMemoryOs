"""Ordered Knowledge provenance shared by API writes, Markdown and retrieval."""

from sqlalchemy import delete

from app.models.content import KnowledgeSource

MAX_SOURCES = 20


def association_ids(value: dict) -> list[str]:
    if "source_ids" in value and value["source_ids"] is not None:
        return list(value["source_ids"])
    return [value["source_id"]] if value.get("source_id") else []


def replace_associations(session, note, identities: list[str]) -> None:
    """Replace ordered links without transient uniqueness failures when reordering."""
    with session.no_autoflush:
        session.execute(delete(KnowledgeSource).where(KnowledgeSource.knowledge_id == note.id),
                        execution_options={"synchronize_session": "fetch"})
        session.expire(note, ["source_links"])
        note.source_links = [KnowledgeSource(source_id=identity, position=index)
                             for index, identity in enumerate(identities)]
        note.source_id = identities[0] if identities else None
