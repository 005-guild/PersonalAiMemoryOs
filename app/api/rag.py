"""Semantic retrieval does not alter knowledge or its Markdown projection."""

import asyncio
from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.agents.errors import AIError
from app.api.rag_schemas import AnswerRead, AskRequest, IndexRequest, SearchRead, SearchRequest
from app.vector.errors import RagError
from app.services.content import ContentError

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@contextmanager
def errors():
    try:
        yield
    except (AIError, RagError) as error:
        raise HTTPException(error.status_code, {"code": error.code}) from None
    except ContentError as error:
        raise HTTPException(error.status_code, str(error)) from None
    except SQLAlchemyError:
        raise HTTPException(503, {"code": "database_unavailable"}) from None


@router.get("/embedding-profiles")
def profiles(request: Request):
    return request.app.state.embedding_registry.describe()


@router.get("/index/status")
def status(request: Request, summary_only: bool = False):
    with errors():
        return request.app.state.rag_index.status(summary_only=summary_only)


@router.get("/index/errors")
def index_errors(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with errors():
        return request.app.state.rag_index.details("errors", offset=offset, limit=limit)


@router.get("/index/excluded")
def index_excluded(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    with errors():
        return request.app.state.rag_index.details("excluded", offset=offset, limit=limit)


@router.post("/index/run", status_code=202)
async def run(payload: IndexRequest, request: Request):
    with errors():
        return await request.app.state.rag_index.request_run(retry_failed=payload.retry_failed)


@router.post("/index/rebuild", status_code=202)
async def rebuild(request: Request):
    with errors():
        return await request.app.state.rag_index.request_run(rebuild=True)


@router.post("/search", response_model=SearchRead)
async def search(payload: SearchRequest, request: Request):
    with errors():
        return await request.app.state.rag_search.search(payload.query, payload.top_k)


@router.post("/ask", response_model=AnswerRead)
async def ask(payload: AskRequest, request: Request):
    with errors():
        prompt = await asyncio.to_thread(request.app.state.processing.templates.snapshot,
            payload.prompt_template_id, payload.prompt_template_version, purpose="rag_qa")
        return await request.app.state.rag_answer.ask(payload.question, payload.top_k, payload.profile_id,
                                                    prompt_snapshot=prompt)
