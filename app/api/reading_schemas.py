"""Public bounded reading projections. Dates describe local knowledge updates."""

from typing import Literal
from pydantic import BaseModel


class ReadingNoteSummary(BaseModel):
    knowledge_id: str
    title: str
    summary: str
    category: str
    tags: list[str]
    updated_at: str
    version: int
    source_title: str
    source_url: str | None
    author: str | None
    match_section: Literal['title', 'summary', 'tag', 'original']
    excerpt: str


class ReadingPage(BaseModel):
    items: list[ReadingNoteSummary]
    total: int
    offset: int
    limit: int


class ReadingCount(BaseModel):
    name: str
    count: int


class ReadingCategory(ReadingCount):
    topic: str


class ReadingOverview(BaseModel):
    total: int
    unavailable_count: int
    topics: list[ReadingCount]
    categories: list[ReadingCategory]
    tags: list[ReadingCount]
    months: list[str]
    recent: list[ReadingNoteSummary]
