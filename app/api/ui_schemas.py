"""Bounded list contracts for the browser workbench."""

from pydantic import BaseModel

from app.api.schemas import RecordRead


class UIOverview(BaseModel):
    active_sources: int
    active_knowledge: int
    ready_drafts: int
    open_conflicts: int


class UISourceSummary(RecordRead):
    title: str
    source_type: str
    author: str | None
    url: str | None
    excerpt: str


class UIKnowledgeSummary(RecordRead):
    title: str
    source_id: str | None
    source_ids: list[str]
    summary: str
    category: str | None
    tags: list[str]
    concepts: list[str]
    deleted: bool
    sync_status: str
    path: str | None


class UISourcePage(BaseModel):
    items: list[UISourceSummary]
    total: int
    offset: int
    limit: int


class UISourceGroup(BaseModel):
    title: str
    source_count: int
    active_count: int
    deleted_count: int
    latest_updated_at: str
    source_types: list[str]


class UISourceGroupPage(BaseModel):
    items: list[UISourceGroup]
    total: int
    total_sources: int
    offset: int
    limit: int


class UIKnowledgePage(BaseModel):
    items: list[UIKnowledgeSummary]
    total: int
    offset: int
    limit: int
