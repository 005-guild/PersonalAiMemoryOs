"""Loopback-only organization control and local collection search."""
import json
import re
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from app.api.settings import _service, _pairs, _invalid_constant, _bounded_structure
from app.services.organization.contracts import OrganizationWrite, OrganizationError, ProfileSwitch
from app.services.organization.search import keyword_search, semantic_search
from app.services.zhihu_sync.storage import safe_path
from app.vector.errors import RagError

router = APIRouter(prefix='/api/v1/collection-organization', tags=['collection-organization'])


async def service(request, mutation=False):
    await _service(request, mutation=mutation)
    target = request.app.state.organization
    if mutation:
        try:
            target.writable()
        except OrganizationError as error:
            raise HTTPException(409, detail={'code': error.code}) from None
    return target


async def body(request):
    data = bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk) > 32*1024:
            raise HTTPException(413, detail={'code':'configuration_too_large'})
        data.extend(chunk)
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        _bounded_structure(value)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, RecursionError):
        raise HTTPException(422, detail={'code':'configuration_invalid'}) from None


async def call(function, *args):
    try:
        return await run_in_threadpool(function, *args)
    except OrganizationError as error:
        raise HTTPException(409, detail={'code':error.code}) from None
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(422, detail={'code':'organization_failed'}) from None


@router.get('')
async def describe(request: Request):
    return await call((await service(request)).describe)


@router.put('')
async def configure(request: Request):
    target = await service(request, True)
    try:
        payload = OrganizationWrite.model_validate(await body(request))
    except ValueError:
        raise HTTPException(422, detail={'code':'configuration_invalid'}) from None
    await call(target.store.save, payload)
    target.wake.set()
    return await call(target.describe)


@router.get('/items')
async def items(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), job_id: str | None = None,
                error: str | None = Query(None,max_length=100)):
    target = await service(request)
    return await call(target.store.items, offset, limit, job_id,error)


@router.post('/switch-profile')
async def switch_profile(request: Request):
    target=await service(request,True)
    try:payload=ProfileSwitch.model_validate(await body(request))
    except ValueError:raise HTTPException(422,detail={'code':'configuration_invalid'}) from None
    result=await call(target.store.switch_profile,payload)
    target.wake.set()
    return result


@router.post('/items/{item_id}/approve-partial-image',status_code=202)
async def approve_partial_image(item_id: str,request: Request):
    target=await service(request,True)
    value=await body(request)
    if set(value)!={'input_hash'} or not isinstance(value['input_hash'],str) or not re.fullmatch('[a-f0-9]{64}',value['input_hash']):
        raise HTTPException(422,detail={'code':'configuration_invalid'})
    await call(target.store.scan)
    result=await call(target.store.approve_partial_image,item_id,value['input_hash'])
    target.wake.set()
    return result


@router.get('/search')
async def search(request: Request, q: str = Query('', max_length=2000), mode: Literal['keyword','semantic']='keyword',
                 category: str = Query('', max_length=80), tag: str = Query('', max_length=80),
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    target = await service(request)
    if mode == 'keyword':
        return await call(keyword_search, target.store, q, category, tag, limit, offset)
    try:
        return await semantic_search(target.store, request.app.state.rag_retrieval, q, category, tag)
    except RagError as error:
        raise HTTPException(error.status_code, detail={'code':error.code}) from None


@router.get('/assets/{name}')
async def asset(name: str, request: Request):
    target = await service(request)
    if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|gif|webp)', name):
        raise HTTPException(404)
    output = await call(target.store.output_directory)
    if not output:
        raise HTTPException(404)
    path = safe_path(Path(output)/'assets'/name)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type={'.png':'image/png','.jpg':'image/jpeg','.gif':'image/gif','.webp':'image/webp'}[path.suffix])


@router.post('/{action}', status_code=202)
async def control(action: str, request: Request):
    target = await service(request, True)
    value = await body(request)
    if set(value)-{'job_id'} or ('job_id' in value and not isinstance(value['job_id'], str)):
        raise HTTPException(422, detail={'code':'configuration_invalid'})
    try:
        return await target.command(action, value.get('job_id'))
    except OrganizationError as error:
        raise HTTPException(409, detail={'code':error.code}) from None
    except Exception:
        raise HTTPException(422, detail={'code':'organization_configuration_invalid'}) from None
