"""Parse submitted export text without reading client paths or linked images."""

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.import_types import (
    MAX_IMPORT_BYTES, ImportFieldError, ImportItemResult, ImportProtocolError,
    ImportReport, ParsedZhihuItem,
)
from app.services.zhihu_frontmatter import split_export
from app.services.zhihu_parser import ZhihuInputItem, _reject_constant, _unique_object, normalize_zhihu_url

MAX_MARKDOWN_FILES = 1000
KNOWN_FIELDS = {"id", "type", "title", "author", "source", "created", "updated", "collected", "downloaded"}
TYPES = {"zhihu-answer": "answer", "zhihu-article": "article", "zhihu-pin": "pin"}
POSITIVE_ID = re.compile(r"[1-9][0-9]*\Z")


class MarkdownImportFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    relative_path: str = Field(min_length=1, max_length=2048)
    content: str


class MarkdownImportDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    files: list[MarkdownImportFile] = Field(min_length=1, max_length=MAX_MARKDOWN_FILES)


class MarkdownImportItemResult(ImportItemResult):
    relative_path: str | None = None
    title: str | None = None
    author: str | None = None
    url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class MarkdownImportReport(ImportReport):
    items: list[MarkdownImportItemResult] = Field(default_factory=list)


@dataclass(frozen=True)
class MarkdownBatch:
    entries: list[ParsedZhihuItem | ImportItemResult]
    metadata: list[dict]

    def report(self, report: ImportReport) -> MarkdownImportReport:
        data = report.model_dump()
        data["items"] = [{**item, **self.metadata[item["index"]]} for item in data["items"]]
        return MarkdownImportReport.model_validate(data)


def _relative_path(value: str) -> str:
    if ("\\" in value or ":" in value or any(ord(character) < 32 for character in value)
            or value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("invalid_relative_path")
    value.encode("utf-8")
    if PurePosixPath(value).suffix.casefold() != ".md":
        raise ValueError("not_markdown")
    return value


def _invalid(index: int, reason: str, field="content") -> ImportItemResult:
    return ImportItemResult(index=index, status="invalid", reason=reason,
                            errors=[ImportFieldError(field=field, message=reason)])


def _entry(index: int, value, seen: set[str]) -> tuple[ParsedZhihuItem | ImportItemResult, dict]:
    meta = {"relative_path": None, "title": None, "author": None, "url": None, "warnings": []}
    if isinstance(value, dict) and isinstance(value.get("relative_path"), str) and len(value["relative_path"]) <= 2048:
        try:
            meta["relative_path"] = _relative_path(value["relative_path"])
        except (ValueError, UnicodeError):
            pass
    try:
        file = MarkdownImportFile.model_validate(value)
    except ValidationError:
        return _invalid(index, "invalid_file_fields", "file"), meta
    try:
        path = _relative_path(file.relative_path)
    except (ValueError, UnicodeError):
        return _invalid(index, "invalid_relative_path", "relative_path"), meta
    meta["relative_path"] = path
    if path.casefold() in seen:
        return _invalid(index, "duplicate_relative_path", "relative_path"), meta
    seen.add(path.casefold())
    if PurePosixPath(path).name.casefold() == "readme.md":
        return ImportItemResult(index=index, status="skipped", reason="directory_index"), meta
    try:
        file.content.encode("utf-8")
        fields, body = split_export(file.content)
    except (ValueError, UnicodeError, RecursionError):
        return _invalid(index, "invalid_frontmatter"), meta
    if set(fields) - KNOWN_FIELDS:
        meta["warnings"] = ["已忽略不支持的附加元数据。"]
    try:
        for name in ("title", "author", "source", "type", "id"):
            if isinstance(fields.get(name), str):
                fields[name].encode("utf-8")
        item = ZhihuInputItem.model_validate({"title": fields.get("title"),
            "author": fields.get("author"), "url": fields.get("source"), "content": body})
    except (ValidationError, UnicodeError):
        return _invalid(index, "invalid_metadata_or_body"), meta
    meta.update(title=item.title, author=item.author)
    try:
        identity = normalize_zhihu_url(item.url)
    except ValueError:
        return _invalid(index, "invalid_url", "source"), meta
    meta["url"] = identity.canonical_url
    if "type" in fields and (type(fields["type"]) is not str
                              or TYPES.get(fields["type"]) != identity.resource_type):
        return _invalid(index, "type_url_mismatch", "type"), meta
    if "id" in fields:
        original_id = fields["id"]
        if (type(original_id) not in {str, int} or not POSITIVE_ID.fullmatch(str(original_id))
                or str(original_id) != identity.external_id):
            return _invalid(index, "id_url_mismatch", "id"), meta
    values = item.model_dump()
    values.update(source_type="zhihu", url=identity.canonical_url)
    return ParsedZhihuItem(index, identity.resource_type, identity.external_id, values), meta


def parse_markdown_document(raw: bytes) -> MarkdownBatch:
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportProtocolError(413, "Import request exceeds 10 MiB.")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise ImportProtocolError(400, "Use valid UTF-8 JSON with unique object keys.") from None
    if (not isinstance(data, dict) or set(data) != {"files"} or not isinstance(data.get("files"), list)
            or not 1 <= len(data["files"]) <= MAX_MARKDOWN_FILES):
        raise ImportProtocolError(422, "Use a files array of 1 to 1000 Markdown files.")
    entries, metadata, seen = [], [], set()
    for index, value in enumerate(data["files"]):
        entry, meta = _entry(index, value, seen)
        entries.append(entry)
        metadata.append(meta)
    return MarkdownBatch(entries, metadata)
