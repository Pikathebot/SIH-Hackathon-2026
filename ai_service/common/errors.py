"""Shared exception types for ai_service modules."""

from typing import Optional

# Canonical error codes defined across contracts
MODEL_INFERENCE_FAILED = "MODEL_INFERENCE_FAILED"
INVALID_MODALITY_COMBINATION = "INVALID_MODALITY_COMBINATION"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
INVALID_IMAGE_COUNT = "INVALID_IMAGE_COUNT"
INTERNAL_ERROR = "INTERNAL_ERROR"


class AIServiceError(Exception):
    """
    Base exception for all AI service errors conforming to AI_SERVICE_CONTRACT.md.
    The backend orchestrator catches this and maps it to HTTP error responses.
    """
    def __init__(self, code: str, message: str, detail: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        if self.detail:
            return f"[{self.code}] {self.message} (Detail: {self.detail})"
        return f"[{self.code}] {self.message}"
