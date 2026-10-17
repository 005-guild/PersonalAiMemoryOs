"""Loopback-only editing of configuration for the next application startup."""

import inspect
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.settings_schemas import AIKeyUpdate, AIProfileWrite, AISettingsWrite
from app.services.ai_settings import AISettingsError

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
MAX_REQUEST_BYTES = 1024 * 1024
SAFE_FIELDS = set(AISettingsWrite.model_fields) | set(AIProfileWrite.model_fields) | set(AIKeyUpdate.model_fields)


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError()
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError()


def _bounded_structure(value):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 32:
            raise ValueError()
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


async def _service(request: Request, *, mutation=False):
    service = getattr(request.app.state, "ai_settings", None)
    guard = getattr(request.app.state, "configuration_guard", None)
    if service is None or guard is None:
        raise HTTPException(503, detail={"code": "configuration_unavailable"})
    outcome = guard(request, csrf_token=service.csrf_token, mutation=mutation)
    if inspect.isawaitable(outcome):
        await outcome
    return service


async def _call(method, *args):
    try:
        return await run_in_threadpool(method, *args)
    except AISettingsError as error:
        raise HTTPException(error.status_code, detail={"code": error.code}) from None


@router.get("/ai")
async def get_ai_settings(request: Request):
    service = await _service(request)
    return await _call(service.describe)


@router.put("/ai")
async def update_ai_settings(request: Request):
    service = await _service(request, mutation=True)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, detail={"code": "configuration_request_too_large"})
        body.extend(chunk)
    try:
        value = json.loads(body, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        _bounded_structure(value)
        payload = AISettingsWrite.model_validate(value)
    except ValidationError as error:
        # Validation messages/context may contain rejected credentials or URLs.
        errors = [{"loc": ["body", *(part if isinstance(part, int) or part in SAFE_FIELDS else "field"
                                     for part in item["loc"])], "type": item["type"], "msg": "Invalid configuration value."}
                  for item in error.errors(include_input=False, include_context=False)]
        raise HTTPException(422, detail=errors) from None
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "configuration_invalid"}) from None
    return await _call(service.save, payload)
