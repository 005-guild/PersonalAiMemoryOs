"""Bounded management projections; loading a page never starts a task."""

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select, func
from app.models import OrganizationItem, OrganizationJob
from app.api.organization import service
from app.services.organization.store import item_view

router = APIRouter(prefix='/api/v1/collection-organization', tags=['collection-organization'])


@router.get('/records')
async def records(request: Request, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100),
                  status: str = Query('', max_length=50), error: str = Query('', max_length=100),
                  job_id: str = Query('', max_length=36)):
    target = await service(request)
    with target.store.database.session() as session:
        query = select(OrganizationItem)
        if status: query = query.where(OrganizationItem.status == status)
        if error: query = query.where(OrganizationItem.error == error)
        if job_id:
            job = session.get(OrganizationJob, job_id)
            if not job: raise HTTPException(404, detail={'code': 'job_not_found'})
            query = query.where(OrganizationItem.id.in_(job.selection))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(OrganizationItem.created_at, OrganizationItem.id).offset(offset).limit(limit))
        return {'items': [item_view(row) for row in rows], 'total': total, 'offset': offset, 'limit': limit}


@router.get('/records/{identifier}')
async def record(identifier: str, request: Request):
    target = await service(request)
    with target.store.database.session() as session:
        row = session.get(OrganizationItem, identifier)
        if not row: raise HTTPException(404, detail={'code': 'item_not_found'})
        return item_view(row, True)


@router.get('/jobs')
async def jobs(request: Request, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100)):
    target = await service(request)
    with target.store.database.session() as session:
        total = session.scalar(select(func.count()).select_from(OrganizationJob))
        rows = session.scalars(select(OrganizationJob).order_by(OrganizationJob.created_at.desc(), OrganizationJob.id).offset(offset).limit(limit))
        return {'items': [{key: getattr(row, key) for key in ('id', 'mode', 'status', 'error', 'created_at', 'finished_at')}
                          | {'count': len(row.selection)} for row in rows], 'total': total, 'offset': offset, 'limit': limit}


@router.get('/jobs/{identifier}')
async def job(identifier: str, request: Request):
    target = await service(request)
    with target.store.database.session() as session:
        row = session.get(OrganizationJob, identifier)
        if not row: raise HTTPException(404, detail={'code': 'job_not_found'})
        return {key: getattr(row, key) for key in ('id', 'mode', 'status', 'error', 'created_at', 'finished_at')} | {'count': len(row.selection)}
