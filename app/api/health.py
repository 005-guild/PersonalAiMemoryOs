"""Database-backed health endpoint."""

import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "unavailable"]


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
def health(request: Request) -> HealthResponse | JSONResponse:
    try:
        request.app.state.database.check_connection()
    except Exception as exc:
        # Driver exception text can include URLs, SQL parameters, or local paths.
        logger.error("Database health check failed (%s).", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"status": "error", "database": "unavailable"},
        )
    return HealthResponse(status="ok", database="ok")
