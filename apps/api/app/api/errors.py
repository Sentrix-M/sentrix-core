"""Global exception handlers.

Domain exceptions are mapped to consistent JSON error envelopes so clients
can programmatically handle failures without scraping status codes or message
strings.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import SentrixError


def register_exception_handlers(app: FastAPI) -> None:
    """Register all domain exception handlers on the FastAPI app."""

    @app.exception_handler(SentrixError)
    async def sentrix_error_handler(
        request: Request, exc: SentrixError  # noqa: ARG001 - FastAPI signature
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                }
            },
        )

