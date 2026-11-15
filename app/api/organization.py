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


@router.get('/quality/{knowledge_id}')
async def quality_view(knowledge_id: str, request: Request):
    from app.services.organization.quality import QualityService
    target = await service(request)
    return await call(QualityService(target).view, knowledge_id)


@router.post('/jobs/{job_id}/retry',status_code=202)
async def retry_extension(job_id: str, request: Request):
    from app.models import OrganizationJob
    target=await service(request,True)
    if await body(request) != {}:raise HTTPException(422,detail={'code':'configuration_invalid'})
    def retry():
        with target.store.transaction() as session:
            target.store.require_idle(session)
            job=session.get(OrganizationJob,job_id)
            if not job or job.mode not in {'topic','quality'} or job.status not in {'failed','paused'}:
                raise OrganizationError('extension_job_not_retryable')
            resolved=target.calls.resolve(job.settings)
            if job.settings.get('profile_fingerprint') not in {None,resolved.fingerprint}:
                raise OrganizationError('organization_profile_changed')
            job.settings={**job.settings,'retry':True};job.status='pending';job.error=None;job.finished_at=None
            control=target.store.control(session);control['paused']=False;target.store.set_control(session,control)
            return {'id':job.id,'status':job.status}
    result=await call(retry);target.wake.set();return result


@router.get('/topics')
async def topic_view(request: Request, topic: str = Query(...,min_length=1,max_length=200)):
    from app.services.topics.service import TopicService
    return await call(TopicService(await service(request)).view, topic)


@router.post('/topics/config')
async def topic_config(request: Request):
    from app.services.topics.service import TopicService
    target = await service(request, True)
    value = await body(request)
    if set(value) != {'enabled'} or type(value['enabled']) is not bool:
        raise HTTPException(422,detail={'code':'configuration_invalid'})
    return await call(TopicService(target).toggle, value['enabled'])


@router.post('/topics/generate',status_code=202)
async def topic_generate(request: Request):
    from app.services.topics.service import TopicService
    target = await service(request, True)
    value = await body(request)
    if (set(value) != {'topic','expected_fingerprint'} or not isinstance(value['topic'],str)
            or not 1 <= len(value['topic']) <= 200 or not isinstance(value['expected_fingerprint'],str)
            or not re.fullmatch('[a-f0-9]{64}',value['expected_fingerprint'])):
        raise HTTPException(422,detail={'code':'configuration_invalid'})
    result = await call(TopicService(target).start,value['topic'],value['expected_fingerprint'])
    target.wake.set()
    return result


@router.post('/quality/{knowledge_id}/{action}')
async def quality_action(knowledge_id: str, action: Literal['generate','adopt'], request: Request):
    from app.services.organization.quality import QualityService
    from app.services.content import ContentError
    target = await service(request, True)
    value = await body(request)
    allowed = {'expected_version', 'candidate_id'} if action == 'adopt' else {'expected_version'}
    if set(value) != allowed or type(value.get('expected_version')) is not int or value['expected_version'] < 1:
        raise HTTPException(422, detail={'code':'configuration_invalid'})
    if action == 'adopt' and (not isinstance(value['candidate_id'], str) or not re.fullmatch('[a-f0-9]{64}', value['candidate_id'])):
        raise HTTPException(422, detail={'code':'configuration_invalid'})
    try:
        result = await call(getattr(QualityService(target), 'start' if action == 'generate' else 'adopt'),
                            knowledge_id, *[value[key] for key in ('expected_version','candidate_id') if key in value])
    except ContentError as error:
        raise HTTPException(error.status_code, detail=error.message) from None
    target.wake.set()
    return result


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
