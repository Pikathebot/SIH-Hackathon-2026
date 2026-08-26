"""
Contract-conformant mock implementation for Optical-SAR Fusion module.
Implements the exact TypedDict shape and signature from AI_SERVICE_CONTRACT.md §3.
"""

import base64
import io
import os
import time
from PIL import Image

from ai_service.common.types import FusionResult, ExecutionMeta
from ai_service.common.errors import (
    AIServiceError,
    INVALID_MODALITY_COMBINATION,
    MODEL_INFERENCE_FAILED,
)


def _get_dummy_classified_regions_base64(size=(128, 128)) -> str:
    """Generate a multi-color segmented classification map as base64 PNG."""
    # Red: Built-up, Green: Vegetation, Blue: Water
    img = Image.new("RGB", size, (34, 139, 34))  # default green vegetation
    # Add a blue water stripe and red urban patch
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], size[1] // 3], fill=(30, 144, 255))  # water
    draw.rectangle([size[0] // 2, size[1] // 2, size[0], size[1]], fill=(220, 20, 60))  # built-up
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _sleep(seconds: float):
    """Sleep with support for MOCK_FAST_MODE override in rapid CI testing."""
    if os.environ.get("MOCK_FAST_MODE", "0") == "1":
        time.sleep(min(seconds, 0.05))
    else:
        time.sleep(seconds)


def run_fusion(
    optical_image: Image.Image,
    sar_image: Image.Image,
    query: str,
) -> FusionResult:
    """
    Must classify at minimum: built-up / water / vegetation regions using both inputs.
    `sar_only_reading` must be a genuine SAR-only interpretation (not just a copy of `answer`).
    Typical latency target: <10s.
    """
    if not isinstance(optical_image, Image.Image) or not isinstance(sar_image, Image.Image):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message="Invalid image inputs: expected two PIL.Image.Image instances",
        )

    # Defensive check: verify modality compatibility if images have metadata tags
    if getattr(optical_image, "_modality", None) == "sar" and getattr(sar_image, "_modality", None) == "sar":
        raise AIServiceError(
            code=INVALID_MODALITY_COMBINATION,
            message="Both submitted images are SAR modality. Fusion requires one optical and one SAR image.",
        )
    if getattr(optical_image, "_modality", None) == "optical" and getattr(sar_image, "_modality", None) == "optical":
        raise AIServiceError(
            code=INVALID_MODALITY_COMBINATION,
            message="Both submitted images are optical modality. Fusion requires one optical and one SAR image.",
        )

    start = time.time()
    _sleep(5.0)
    elapsed_ms = int((time.time() - start) * 1000)

    classified_b64 = _get_dummy_classified_regions_base64()

    return {
        "answer": (
            "Multi-sensor fusion classified the region into 38% dense vegetation canopy, "
            "34% high-dielectric built-up structures, and 28% calm open water bodies. "
            "Optical spectral bands confirmed healthy chlorophyll reflectance while SAR validated structural corner reflectors."
        ),
        "classified_regions_base64": classified_b64,
        "sar_only_reading": (
            "Standalone SAR backscatter intensity reveals strong double-bounce reflections in the southern quadrant (built-up structures), "
            "specular low-return reflection in the north (water reservoir), and intermediate volume scattering across central terrain."
        ),
        "confidence": 0.76,
        "meta": {
            "tool_used": "fusion_classifier",
            "parameters": {
                "classifier_type": "heuristic_stacked_spectral_sar",
                "classes": ["built-up", "water", "vegetation"],
                "confidence_source": "heuristic",
            },
            "latency_ms": elapsed_ms,
        },
    }
