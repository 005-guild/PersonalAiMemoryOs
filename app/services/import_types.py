"""Shared import contracts; reports never include submitted source bodies."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ITEMS = 500


@dataclass(frozen=True)
class ParsedZhihuItem:
    index: int
    resource_type: str
    external_id: str
    values: dict


class ImportFieldError(BaseModel):
    field: str
    message: str


class ImportItemResult(BaseModel):
    index: int
    status: Literal["created", "skipped", "invalid", "would_create", "failed"]
    reason: str
    resource_type: str | None = None
    external_id: str | None = None
    source_id: str | None = None
    version: int | None = None
    differing_fields: list[str] = Field(default_factory=list)
    matched_source_ids: list[str] = Field(default_factory=list)
    errors: list[ImportFieldError] = Field(default_factory=list)


class ImportReport(BaseModel):
    dry_run: bool
    total: int
    processed: int = 0
    created: int = 0
    skipped: int = 0
    invalid: int = 0
    would_create: int = 0
    failed: int = 0
    items: list[ImportItemResult] = Field(default_factory=list)

    def add(self, result: ImportItemResult) -> None:
        self.items.append(result)
        self.processed += 1
        setattr(self, result.status, getattr(self, result.status) + 1)


class ImportProtocolError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


class ImportUnavailable(Exception):
    def __init__(self, report: ImportReport):
        super().__init__("Database temporarily unavailable.")
        self.report = report
