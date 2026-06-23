"""
responses.py
============
Standardized JSON response helpers for the MCQ Generator backend API.

All API routes should use these helpers to ensure consistent response shapes
that are safe to send to the frontend.

Success shape
-------------
    { "success": true, "data": <any> }

Error shape
-----------
    { "success": false, "error": "<user-friendly message>" }
"""

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from exceptions import DocumentProcessingError


def success_response(data: dict | list | None = None, status_code: int = 200) -> JSONResponse:
    """
    Build a standardized success JSON response.

    Parameters
    ----------
    data : dict or list, optional
        The payload to include under the "data" key.
    status_code : int
        HTTP status code (default 200).

    Returns
    -------
    JSONResponse
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data if data is not None else {},
        },
    )


def error_response(user_message: str, status_code: int = 500) -> JSONResponse:
    """
    Build a standardized error JSON response safe to send to the frontend.

    Internal error details (stack traces, paths) must NOT be included here.

    Parameters
    ----------
    user_message : str
        A human-readable, sanitized error description.
    status_code : int
        HTTP status code (default 500).

    Returns
    -------
    JSONResponse
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": user_message,
        },
    )


def raise_http_from_pipeline_error(exc: DocumentProcessingError) -> None:
    """
    Convert a DocumentProcessingError into a FastAPI HTTPException.

    This ensures the frontend always receives a clean JSON error with no
    internal implementation details.

    Parameters
    ----------
    exc : DocumentProcessingError
        The pipeline exception to convert.

    Raises
    ------
    HTTPException
    """
    raise HTTPException(
        status_code=exc.http_status,
        detail={
            "success": False,
            "error": exc.user_message,
        },
    )
