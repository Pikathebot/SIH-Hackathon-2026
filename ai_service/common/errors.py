"""
Shared error types for SatQuery AI service layer.

Defined once here, raised by AI modules, caught by the backend orchestrator.
Per AI_SERVICE_CONTRACT.md §2 and §3 — error behavior.
"""


class AIServiceError(Exception):
    """
    Base exception for all AI service errors.

    The orchestrator catches this and maps it to the appropriate HTTP error
    code per API_CONTRACT.md §1.

    Attributes:
        code: One of the canonical error codes:
              - "MODEL_INFERENCE_FAILED" — OOM, malformed image, checkpoint not loaded
              - "INVALID_MODALITY_COMBINATION" — e.g. fusion given two same-modality images
        message: Human-readable error description.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")
