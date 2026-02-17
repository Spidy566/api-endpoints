"""
---------------------------------------------------------------------------
Commit History
---------------------------------------------------------------------------
Description                              | Date       | Developer
---------------------------------------------------------------------------
Validation exception handlers            | 07-01-2026 | vishal
---------------------------------------------------------------------------
"""
from fastapi import Request
from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from core.config import logger

async def validation_exception_handler(_: Request, exc: ResponseValidationError):
    """Overrides the default 500 error for validation failures."""
    logger.error(f"Response Validation Error: {exc.errors()}")
    return JSONResponse(
        status_code=500,
        content={
            "message": "Server Response Validation Failed",
            "details": exc.errors()
        }
    )