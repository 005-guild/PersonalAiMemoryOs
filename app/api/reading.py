"""Loopback-only GET views; no jobs, indexing, or model generation on browsing."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from app.api.organization import service
from app.api.reading_schemas import ReadingOverview, ReadingPage
from app.services.content import ContentError
from app.services.reading import ReadingService

router = APIRouter(prefix='/api/v1/reading', tags=['reading'])


async def invoke(request, method, *args, **kwargs):
    target = ReadingService((await service(request)).store)
    try:
        return await run_in_threadpool(getattr(target, method), *args, **kwargs)
    except ContentError as error:
        raise HTTPException(error.status_code, detail={'code': error.message}) from None


@router.get('/overview', response_model=ReadingOverview)
async def overview(request: Request):
    return await invoke(request, 'overview')


@router.get('/notes', response_model=ReadingPage)
async def notes(request: Request, q: str = Query('', max_length=2000),
                topic: str = Query('', max_length=200), category: str = Query('', max_length=200),
                tag: str = Query('', max_length=200),
                updated_month: str = Query('', pattern=r'^(?:\d{4}-(?:0[1-9]|1[0-2]))?$'),
                sort: Literal['updated_desc', 'title_asc'] = 'updated_desc',
                offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    return await invoke(request, 'notes', q=q, topic=topic, category=category, tag=tag,
                        updated_month=updated_month, sort=sort, offset=offset, limit=limit)


@router.get('/notes/{knowledge_id}')
async def detail(knowledge_id: UUID, request: Request):
    return await invoke(request, 'detail', str(knowledge_id))
