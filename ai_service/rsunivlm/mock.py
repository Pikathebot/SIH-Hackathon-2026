"""
Contract-conformant mock implementation for RSUniVLM module.
Implements the exact TypedDict shapes and signatures from AI_SERVICE_CONTRACT.md §2.
"""

import base64
import io
import os
import time
from typing import Literal, Optional
from PIL import Image

from ai_service.common.types import (
    VQAResult,
    CaptioningResult,
    DetectionResult,
    ChangeResult,
    ExecutionMeta,
)
from ai_service.common.errors import AIServiceError, MODEL_INFERENCE_FAILED


def _get_dummy_png_base64(color=(255, 0, 0, 128), size=(128, 128)) -> str:
    """Generate a valid base64-encoded RGBA PNG for mock visual evidence."""
    img = Image.new("RGBA", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _sleep(seconds: float):
    """Sleep with support for MOCK_FAST_MODE override or pytest in rapid CI testing."""
    if os.environ.get("MOCK_FAST_MODE", "0") == "1" or "pytest" in sys.modules:
        time.sleep(min(seconds, 0.01))
    else:
        time.sleep(seconds)


def run_vqa(image: Image.Image, question: str) -> VQAResult:
    """
    Prompt tag: [VQA]. Typical latency ~0.4-2s.
    """
    if not isinstance(image, Image.Image):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message="Invalid image input: expected PIL.Image.Image instance",
        )

    start = time.time()
    _sleep(0.5)
    elapsed_ms = int((time.time() - start) * 1000)

    # Context-aware mock answer
    q_lower = question.lower()
    if "court" in q_lower or "basketball" in q_lower:
        ans = "2 basketball courts are visible in the image."
    elif "count" in q_lower or "how many" in q_lower:
        ans = "4 target structures were identified in the area of interest."
    else:
        ans = "The visual query corresponds to a mixed commercial and residential zone."

    return {
        "answer": ans,
        "confidence": 0.85,
        "meta": {
            "tool_used": "rsunivlm_vqa",
            "parameters": {
                "prompt_tag": "[VQA]",
                "question": question,
                "confidence_source": "heuristic",
            },
            "latency_ms": elapsed_ms,
        },
    }


def run_captioning(image: Image.Image) -> CaptioningResult:
    """
    Prompt tag: [CAP]. Typical latency ~1-2s.
    """
    if not isinstance(image, Image.Image):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message="Invalid image input: expected PIL.Image.Image instance",
        )

    start = time.time()
    _sleep(1.5)
    elapsed_ms = int((time.time() - start) * 1000)

    return {
        "caption": "The satellite imagery displays an urbanized land-cover scene with built-up infrastructure, paved roads, and scattered green vegetation parcels.",
        "confidence": 0.80,
        "meta": {
            "tool_used": "rsunivlm_cap",
            "parameters": {
                "prompt_tag": "[CAP]",
                "confidence_source": "heuristic",
            },
            "latency_ms": elapsed_ms,
        },
    }


def run_detection(
    image: Image.Image,
    query: str,
    mode: Literal["auto", "bbox", "mask"] = "auto",
) -> DetectionResult:
    """
    mode='auto' routing rule per AI_SERVICE_CONTRACT.md §2:
      - query contains any of: 'where', 'locate', 'find', 'box' -> use [VG] bounding box (~1.7-2s)
      - query contains any of: 'highlight', 'segment', 'mask'   -> use [SEG] pixel mask (~29-36s)
      - otherwise default to [VG] (fast path) unless query explicitly requests a mask
    """
    if not isinstance(image, Image.Image):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message="Invalid image input: expected PIL.Image.Image instance",
        )

    q_lower = query.lower()

    # Route mode
    if mode == "auto":
        if any(w in q_lower for w in ["highlight", "segment", "mask"]):
            resolved_mode = "mask"
        elif any(w in q_lower for w in ["where", "locate", "find", "box"]):
            resolved_mode = "bbox"
        else:
            resolved_mode = "bbox"
    else:
        resolved_mode = mode

    start = time.time()

    if resolved_mode == "bbox":
        _sleep(2.0)
        elapsed_ms = int((time.time() - start) * 1000)
        w, h = image.size
        # Bounding boxes in pixel coords [x1, y1, x2, y2] relative to image size
        boxes = [[int(0.15 * w), int(0.20 * h), int(0.75 * w), int(0.85 * h)]]
        return {
            "mode": "bbox",
            "boxes": boxes,
            "mask_base64": None,
            "overlay_base64": None,
            "confidence": 0.75,
            "meta": {
                "tool_used": "rsunivlm_vg",
                "parameters": {
                    "prompt_tag": "[VG]",
                    "resolved_mode": "bbox",
                    "confidence_source": "heuristic",
                },
                "latency_ms": elapsed_ms,
            },
        }
    else:
        _sleep(30.0)
        elapsed_ms = int((time.time() - start) * 1000)
        mask_b64 = _get_dummy_png_base64(color=(255, 255, 255, 255))
        overlay_b64 = _get_dummy_png_base64(color=(0, 0, 255, 128))
        return {
            "mode": "mask",
            "boxes": None,
            "mask_base64": mask_b64,
            "overlay_base64": overlay_b64,
            "confidence": 0.75,
            "meta": {
                "tool_used": "rsunivlm_seg",
                "parameters": {
                    "prompt_tag": "[SEG]",
                    "resolved_mode": "mask",
                    "confidence_source": "heuristic",
                },
                "latency_ms": elapsed_ms,
            },
        }


def run_change_detection(
    image_before: Image.Image,
    image_after: Image.Image,
    query: Optional[str] = None,
) -> ChangeResult:
    """
    Prompt tag: [CCD] for the answer text; [SEG] on the pair if a mask is requested/needed.
    Typical latency: [CCD] ~4s, [SEG]-based mask ~26-36s.
    """
    if not isinstance(image_before, Image.Image) or not isinstance(image_after, Image.Image):
        raise AIServiceError(
            code=MODEL_INFERENCE_FAILED,
            message="Invalid image inputs: expected two PIL.Image.Image instances",
        )

    start = time.time()
    _sleep(4.0)
    elapsed_ms = int((time.time() - start) * 1000)

    mask_b64 = _get_dummy_png_base64(color=(255, 255, 255, 255))
    overlay_b64 = _get_dummy_png_base64(color=(255, 0, 0, 128))

    return {
        "answer": "Significant new commercial building construction and road network expansion detected in the northeastern quadrant between the two acquisition dates.",
        "mask_base64": mask_b64,
        "overlay_base64": overlay_b64,
        "confidence": 0.78,
        "meta": {
            "tool_used": "rsunivlm_ccd",
            "parameters": {
                "prompt_tag": "[CCD]",
                "query": query,
                "confidence_source": "heuristic",
            },
            "latency_ms": elapsed_ms,
        },
    }
