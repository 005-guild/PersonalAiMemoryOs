"""Parse the project's offline JSON protocol without network or database IO."""

import json
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.fields import MAX_BODY_LENGTH, Title
from app.services.import_types import (
    MAX_IMPORT_BYTES, MAX_IMPORT_ITEMS, ImportFieldError, ImportItemResult,
    ImportProtocolError, ParsedZhihuItem,
)

ANSWER = re.compile(r"/question/([1-9][0-9]*)/answer/([1-9][0-9]*)/?\Z")
ARTICLE = re.compile(r"/p/([1-9][0-9]*)/?\Z")
PIN = re.compile(r"/pin/([1-9][0-9]*)/?\Z")


@dataclass(frozen=True)
class ZhihuIdentity:
    resource_type: str
    external_id: str
    canonical_url: str


def normalize_zhihu_url(value: str) -> ZhihuIdentity:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("Use a Zhihu answer, article or pin URL of at most 4096 characters.")
    value = value.strip()
    if any(character.isspace() or ord(character) < 32 or character == "\\" for character in value):
        raise ValueError("The URL contains unsupported characters.")
    try:
        url = urlsplit(value)
        if (url.scheme.lower() not in {"http", "https"} or url.username is not None
                or url.password is not None or url.port is not None):
            raise ValueError
        host = (url.hostname or "").lower()
    except ValueError:
        raise ValueError("Use an HTTP(S) Zhihu URL without credentials or a port.") from None
    if host in {"zhihu.com", "www.zhihu.com"} and (match := ANSWER.fullmatch(url.path)):
        question, answer = match.groups()
        return ZhihuIdentity("answer", answer,
                             f"https://www.zhihu.com/question/{question}/answer/{answer}")
    if host == "zhuanlan.zhihu.com" and (match := ARTICLE.fullmatch(url.path)):
        article = match.group(1)
        return ZhihuIdentity("article", article, f"https://zhuanlan.zhihu.com/p/{article}")
    if host in {"zhihu.com", "www.zhihu.com"} and (match := PIN.fullmatch(url.path)):
        pin = match.group(1)
        return ZhihuIdentity("pin", pin, f"https://www.zhihu.com/pin/{pin}")
    raise ValueError("Only Zhihu answer, column article and pin URLs are supported.")


class ZhihuInputItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str = Field(max_length=4096)
    title: Title
    author: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_BODY_LENGTH)

    @model_validator(mode="after")
    def require_body(self):
        if not self.content.strip():
            raise ValueError("content must contain non-whitespace text.")
        try:
            for value in (self.url, self.title, self.author, self.content):
                if value is not None:
                    value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Text fields must contain valid UTF-8 text.") from None
        return self


class ZhihuImportDocument(BaseModel):
    """OpenAPI documentation; actual validation handles each item independently."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    items: list[ZhihuInputItem] = Field(min_length=1, max_length=MAX_IMPORT_ITEMS)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object keys are not supported.")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON numbers are not supported.")


def parse_import_document(raw: bytes) -> list[ParsedZhihuItem | ImportItemResult]:
    if len(raw) > MAX_IMPORT_BYTES:
        raise ImportProtocolError(413, "Import request exceeds 10 MiB.")
    try:
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise ImportProtocolError(400, "Use valid UTF-8 JSON with unique object keys.") from None
    if (not isinstance(data, dict) or set(data) != {"schema_version", "items"}
            or type(data.get("schema_version")) is not int or data["schema_version"] != 1
            or not isinstance(data.get("items"), list)
            or not 1 <= len(data["items"]) <= MAX_IMPORT_ITEMS):
        raise ImportProtocolError(422, "Use schema_version 1 and an items array of 1 to 500 entries.")
    entries = []
    for index, value in enumerate(data["items"]):
        try:
            item = ZhihuInputItem.model_validate(value)
        except ValidationError as exc:
            errors = [ImportFieldError(
                field=".".join(str(part) for part in error["loc"]) or "content",
                message=error["msg"],
            ) for error in exc.errors(include_input=False, include_context=False, include_url=False)]
            entries.append(ImportItemResult(index=index, status="invalid",
                                            reason="validation_error", errors=errors))
            continue
        try:
            identity = normalize_zhihu_url(item.url)
        except ValueError as exc:
            entries.append(ImportItemResult(index=index, status="invalid", reason="invalid_url",
                                            errors=[ImportFieldError(field="url", message=str(exc))]))
            continue
        values = item.model_dump()
        values.update(source_type="zhihu", url=identity.canonical_url)
        entries.append(ParsedZhihuItem(index, identity.resource_type, identity.external_id, values))
    return entries
