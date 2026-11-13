"""Protected local configuration and explicit Zhihu synchronization commands."""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.settings import _service, _pairs, _invalid_constant
from app.services.zhihu_sync.configuration import SyncConfigurationWrite
from app.services.zhihu_sync.storage import SyncError

router = APIRouter(prefix='/api/v1/settings/zhihu-sync', tags=['settings'])


async def service(request, mutation=False):
    await _service(request, mutation=mutation)
    return request.app.state.zhihu_sync


async def call(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except SyncError as error:
        code = str(error)
        status = 409 if code in {'configuration_changed', 'sync_busy', 'target_busy'} else 422
        raise HTTPException(status_code=status, detail={'code':code}) from None


@router.get('')
async def describe(request: Request):
    return await call((await service(request)).describe)


@router.put('')
async def configure(request: Request):
    target = await service(request, True)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16 * 1024:
            raise HTTPException(413, detail={'code':'configuration_too_large'})
    try:
        payload = SyncConfigurationWrite.model_validate(json.loads(body, object_pairs_hook=_pairs,
                                                                   parse_constant=_invalid_constant))
    except (ValueError, UnicodeError, ValidationError, RecursionError):
        raise HTTPException(422, detail={'code':'configuration_invalid'}) from None
    return await call(target.save, payload)


@router.post('/{action}', status_code=202)
async def control(action: str, request: Request):
    target = await service(request, True)
    if action == 'stop':
        return await call(target.stop_current)
    if action not in {'login', 'preview', 'run'}:
        raise HTTPException(404, detail={'code':'unknown_action'})
    return await call(target.submit, action)
