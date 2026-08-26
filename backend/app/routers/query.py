"""
Query endpoint — POST /api/v1/query

The single demo-critical endpoint per API_CONTRACT.md §1.
All errors are caught and returned in the contracted JSON error shape.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ai_service.common.errors import AIServiceError
from app.models.api import ErrorDetail, ErrorResponse, QueryRequest, QueryResponse
from app.orchestrator import QueryValidationError, process_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def submit_query(request: QueryRequest) -> QueryResponse:
    """
    POST /api/v1/query — submit a natural-language query with 1–2 images.

    Validates inputs, classifies intent, dispatches to the appropriate AI
    function, and returns the result with execution_summary.
    """
    try:
        return await process_query(request)

    except QueryValidationError as exc:
        # Input validation failed → 400
        # Error code mapping per API_CONTRACT.md §1:
        #   INVALID_IMAGE_COUNT → 400
        #   INVALID_MODALITY_COMBINATION → 400
        #   UNSUPPORTED_FORMAT → 400
        logger.warning("Validation error: [%s] %s", exc.code, exc.message)
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=exc.code,
                    message=exc.message,
                    detail=exc.detail,
                )
            ).model_dump(),
        )

    except AIServiceError as exc:
        # AI service error → map to HTTP status per API_CONTRACT.md §1
        logger.error("AI service error: [%s] %s", exc.code, exc.message)

        status_map = {
            "MODEL_INFERENCE_FAILED": 502,
            "INVALID_MODALITY_COMBINATION": 400,
        }
        status_code = status_map.get(exc.code, 500)

        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                error=ErrorDetail(
                    code=exc.code,
                    message=exc.message,
                )
            ).model_dump(),
        )

    except Exception as exc:
        # Unexpected error → 500 INTERNAL_ERROR
        # The backend must never let an unhandled exception produce a bare 500
        # with no JSON body (API_CONTRACT.md §1).
        logger.exception("Unexpected error processing query")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="An unexpected error occurred while processing the query.",
                    detail=str(exc),
                )
            ).model_dump(),
        )
