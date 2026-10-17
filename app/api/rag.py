"""Semantic retrieval does not alter knowledge or its Markdown projection."""

from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.agents.errors import AIError
from app.api.rag_schemas import AnswerRead, AskRequest, IndexRequest, SearchRead, SearchRequest
from app.vector.errors import RagError

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


@contextmanager
def errors():
    try:
        yield
    except (AIError, RagError) as error:
        raise HTTPException(error.status_code, {"code": error.code}) from None
    except SQLAlchemyError:
        raise HTTPException(503, {"code": "database_unavailable"}) from None


@router.get("/embedding-profiles")
def profiles(request: Request):
    return request.app.state.embedding_registry.describe()


@router.get("/index/status")
def status(request: Request):
    with errors():
        return request.app.state.rag_index.status()


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
        return await request.app.state.rag_answer.ask(payload.question, payload.top_k, payload.profile_id)
