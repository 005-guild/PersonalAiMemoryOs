"""Loopback configuration and explicitly triggered RAG connectivity checks."""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.api.rag_settings_schemas import EmbeddingProfileWrite, RAGSettingsTest, RAGSettingsWrite
from app.api.settings import MAX_REQUEST_BYTES, _bounded_structure, _call, _invalid_constant, _pairs, _service
from app.api.settings_schemas import AIKeyUpdate
from app.services.rag_settings_state import RAGSettingsError

router = APIRouter(prefix="/api/v1/settings/rag", tags=["settings"])
SAFE_FIELDS = set(RAGSettingsWrite.model_fields) | set(EmbeddingProfileWrite.model_fields) | set(AIKeyUpdate.model_fields) | set(RAGSettingsTest.model_fields)


async def _rag(request, *, mutation=False):
    await _service(request, mutation=mutation)
    service = getattr(request.app.state, "rag_settings", None)
    if service is None:
        raise HTTPException(503, detail={"code": "configuration_unavailable"})
    return service


async def _payload(request, schema):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise HTTPException(413, detail={"code": "configuration_request_too_large"})
        body.extend(chunk)
    try:
        value = json.loads(body, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        _bounded_structure(value)
        return schema.model_validate(value)
    except ValidationError as error:
        errors = [{"loc": ["body", *(part if isinstance(part, int) or part in SAFE_FIELDS else "field" for part in item["loc"])],
                   "type": item["type"], "msg": "Invalid configuration value."}
                  for item in error.errors(include_input=False, include_context=False)]
        raise HTTPException(422, detail=errors) from None
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "configuration_invalid"}) from None


def _desktop(request, result):
    return {**result, "desktop": {"restart_supported": getattr(request.app.state, "desktop_restarter", None) is not None}}


@router.get("")
async def get_rag_settings(request: Request):
    service = await _rag(request)
    return _desktop(request, await _call(service.describe))


@router.put("")
async def update_rag_settings(request: Request):
    service = await _rag(request, mutation=True)
    return _desktop(request, await _call(service.save, await _payload(request, RAGSettingsWrite)))


@router.post("/test")
async def test_rag_settings(request: Request):
    service = await _rag(request, mutation=True)
    payload = await _payload(request, RAGSettingsTest)
    try:
        return await service.probes.run(payload)
    except RAGSettingsError as error:
        raise HTTPException(error.status_code, detail={"code": error.code}) from None
