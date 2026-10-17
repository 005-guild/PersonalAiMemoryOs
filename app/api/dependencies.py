"""Request units of work keep the synchronization lock on the handler thread."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.services.content import ContentError


@contextmanager
def request_session(request: Request) -> Iterator[Session]:
    """Call inside a synchronous handler, never as a FastAPI yield dependency."""
    with request.app.state.sync_lock:
        with request.app.state.database.session() as session:
            try:
                yield session
                session.commit()
            except ContentError as exc:
                session.rollback()
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
            except StaleDataError:
                session.rollback()
                raise HTTPException(status_code=409, detail="The record changed; reload its current version.") from None
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail="The change conflicts with existing records.") from None
            except OperationalError:
                session.rollback()
                raise HTTPException(status_code=503, detail="Database temporarily unavailable.") from None
