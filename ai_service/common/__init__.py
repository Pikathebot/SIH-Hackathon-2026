"""Common types and errors shared across ai_service modules."""

from .types import (
    Modality,
    ExecutionMeta,
    VQAResult,
    CaptioningResult,
    DetectionResult,
    ChangeResult,
    FusionResult,
)
from .errors import (
    AIServiceError,
    MODEL_INFERENCE_FAILED,
    INVALID_MODALITY_COMBINATION,
    UNSUPPORTED_FORMAT,
    INVALID_IMAGE_COUNT,
    INTERNAL_ERROR,
)

__all__ = [
    "Modality",
    "ExecutionMeta",
    "VQAResult",
    "CaptioningResult",
    "DetectionResult",
    "ChangeResult",
    "FusionResult",
    "AIServiceError",
    "MODEL_INFERENCE_FAILED",
    "INVALID_MODALITY_COMBINATION",
    "UNSUPPORTED_FORMAT",
    "INVALID_IMAGE_COUNT",
    "INTERNAL_ERROR",
]
