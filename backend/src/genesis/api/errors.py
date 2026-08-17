"""Consistent error shape.

The frontend renders `detail` directly to the user, so it must always be a
short, safe sentence — never a stack trace, never a raw database message.
Unexpected exceptions are logged in full and reported generically.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from genesis.domain.pipeline import TransitionError

log = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TransitionError)
    async def _transition_error(_: Request, exc: TransitionError) -> JSONResponse:
        # An invalid pipeline move is a user mistake, not a server fault.
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our side. Please try again."},
        )
