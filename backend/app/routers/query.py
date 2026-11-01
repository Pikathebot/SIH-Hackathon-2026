"""
Query endpoint — POST /api/v1/query

The core endpoint per API_CONTRACT.md §1 (v2.0.0: authenticated, optional
images[].asset_id and session_id). All errors are returned in the contracted
JSON error shape.
"""

import logging

from fastapi import APIRouter

from ai_service.common.errors import AIServiceError
from app.errors import error_response
from app.models.api import ErrorResponse, QueryRequest, QueryResponse
from app.orchestrator import QueryValidationError, process_query
from app.security import CurrentUser, DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])

_AI_STATUS = {"MODEL_INFERENCE_FAILED": 502, "INVALID_MODALITY_COMBINATION": 400}


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def submit_query(request: QueryRequest, user: CurrentUser, db: DbSession) -> QueryResponse:
    """
    POST /api/v1/query — submit a natural-language query with 1–2 images.

    Validates inputs and ownership, classifies intent, dispatches to the AI
    engine, stores the result in the caller's history and returns it with
    execution_summary. ApiError (401/404) propagates to the global handler.
    """
    try:
        return await process_query(request, user=user, db=db)

    except QueryValidationError as exc:
        logger.warning("Validation error: [%s] %s", exc.code, exc.message)
        return error_response(400, exc.code, exc.message, exc.detail)

    except AIServiceError as exc:
        logger.error("AI service error: [%s] %s", exc.code, exc.message)
        return error_response(_AI_STATUS.get(exc.code, 500), exc.code, exc.message)
