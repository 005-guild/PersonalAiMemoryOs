"""Bounded JSON ingestion; business transactions run off the event loop."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.services.import_types import (
    MAX_IMPORT_BYTES, ImportProtocolError, ImportReport, ImportUnavailable,
)
from app.services.importer import ImportService
from app.services.zhihu_parser import ZhihuImportDocument, parse_import_document
from app.services.zhihu_markdown import (
    MarkdownImportDocument, MarkdownImportReport, parse_markdown_document,
)

router = APIRouter(prefix="/api/v1/imports", tags=["imports"])
_body_schema = ZhihuImportDocument.model_json_schema()
_body_schema["properties"]["items"]["items"] = _body_schema.pop("$defs")["ZhihuInputItem"]
_markdown_schema = MarkdownImportDocument.model_json_schema()
_markdown_schema["properties"]["files"]["items"] = _markdown_schema.pop("$defs")["MarkdownImportFile"]


def _import(database, lock, raw, dry_run):
    entries = parse_import_document(raw)
    return ImportService(database, lock).run(entries, dry_run=dry_run)


def _import_markdown(database, lock, raw, dry_run):
    batch = parse_markdown_document(raw)
    try:
        return batch.report(ImportService(database, lock).run(batch.entries, dry_run=dry_run))
    except ImportUnavailable as exc:
        raise ImportUnavailable(batch.report(exc.report)) from None


async def _read_body(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(415, "Use Content-Type: application/json.")
    chunks, size = [], 0
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_IMPORT_BYTES:
                raise HTTPException(413, "Import request exceeds 10 MiB.")
            chunks.append(chunk)
    except ClientDisconnect:
        raise HTTPException(400, "Import request body was incomplete.") from None
    return b"".join(chunks)


async def _submit(request: Request, dry_run: bool, importer):
    raw = await _read_body(request)
    try:
        return await run_in_threadpool(
            importer, request.app.state.database, request.app.state.sync_lock, raw, dry_run,
        )
    except ImportProtocolError as exc:
        raise HTTPException(exc.status_code, str(exc)) from None
    except ImportUnavailable as exc:
        return JSONResponse(status_code=503, content={
            "detail": str(exc), "report": exc.report.model_dump(),
        })


@router.post(
    "/zhihu", response_model=ImportReport,
    responses={400: {"description": "Invalid UTF-8 or JSON"},
               413: {"description": "Request exceeds 10 MiB"},
               415: {"description": "Use application/json"},
               422: {"description": "Invalid document protocol"},
               503: {"description": "Database unavailable; response includes partial report"}},
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
        "schema": _body_schema,
        "example": {"schema_version": 1, "items": [{
            "url": "https://www.zhihu.com/question/123/answer/456",
            "title": "示例回答", "author": "示例作者", "content": "已经整理好的原始正文。",
        }]},
    }}}},
)
async def import_zhihu(request: Request, dry_run: bool = Query(False)):
    return await _submit(request, dry_run, _import)


@router.post(
    "/zhihu-markdown", response_model=MarkdownImportReport,
    responses={400: {"description": "Invalid UTF-8 or JSON"},
               413: {"description": "Request exceeds 10 MiB"},
               415: {"description": "Use application/json"},
               422: {"description": "Use a files array of 1 to 1000 files"},
               503: {"description": "Database unavailable; includes partial report"}},
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {
        "schema": _markdown_schema,
        "example": {"files": [{"relative_path": "articles/example.md", "content":
            '---\ntitle: 示例资料\nauthor: 示例作者\nsource: https://www.zhihu.com/pin/123\n'
            'type: zhihu-pin\nid: "123"\n---\n已经整理好的原始正文。\n'}]},
    }}}},
)
async def import_zhihu_markdown(request: Request, dry_run: bool = Query(False)):
    return await _submit(request, dry_run, _import_markdown)
