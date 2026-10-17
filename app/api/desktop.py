"""Desktop-only lifecycle actions protected like configuration writes."""

from fastapi import APIRouter, HTTPException, Request

from app.api.settings import _service, _call

router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])


@router.post("/restart", status_code=202)
async def restart(request: Request):
    service = await _service(request, mutation=True)
    restarter = getattr(request.app.state, "desktop_restarter", None)
    if restarter is None:
        raise HTTPException(409, detail={"code": "desktop_restart_unavailable"})
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2048:
            raise HTTPException(413, detail={"code": "configuration_request_too_large"})
    import json
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"expected_revision"}:
            raise ValueError()
        snapshot = await _call(service.describe)
        if payload["expected_revision"] != snapshot["revision"]:
            raise HTTPException(409, detail={"code": "configuration_changed"})
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, detail={"code": "configuration_invalid"}) from None
    if not restarter.request():
        raise HTTPException(409, detail={"code": "desktop_restart_busy"})
    return {"status": "restarting"}
