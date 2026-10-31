"""
Contract-conformant mock for the Qwen-VL engine (INTEGRATION_GUIDE.md §2).

THIS IS NOT REAL INFERENCE. It reuses the RSUniVLM mock's canned outputs and
re-labels `tool_used` / parameters so the backend, DB and frontend can be
exercised end-to-end for the `qwen` engine without a GPU or llama-server.
"""

from __future__ import annotations

from typing import Literal, Optional

from PIL import Image

from ai_service.common.types import CaptioningResult, ChangeResult, DetectionResult, VQAResult
from ai_service.rsunivlm import mock as _base

_TOOL_MAP = {
    "rsunivlm_vqa": "qwen_vl_vqa",
    "rsunivlm_cap": "qwen_vl_cap",
    "rsunivlm_vg": "qwen_vl_vg",
    "rsunivlm_seg": "qwen_vl_seg",
    "rsunivlm_ccd": "qwen_vl_ccd",
}


def _relabel(result: dict) -> dict:
    meta = result["meta"]
    meta["tool_used"] = _TOOL_MAP.get(meta["tool_used"], meta["tool_used"])
    params = dict(meta.get("parameters") or {})
    params.pop("prompt_tag", None)
    params["model"] = "mock"
    params["confidence_source"] = "heuristic"
    meta["parameters"] = params
    return result


def run_vqa(image: Image.Image, question: str) -> VQAResult:
    return _relabel(_base.run_vqa(image, question))


def run_captioning(image: Image.Image) -> CaptioningResult:
    return _relabel(_base.run_captioning(image))


def run_detection(
    image: Image.Image,
    query: str,
    mode: Literal["auto", "bbox", "mask"] = "auto",
) -> DetectionResult:
    return _relabel(_base.run_detection(image, query, mode=mode))


def run_change_detection(
    image_before: Image.Image,
    image_after: Image.Image,
    query: Optional[str] = None,
) -> ChangeResult:
    return _relabel(_base.run_change_detection(image_before, image_after, query))


def classify_intent(query: str, modalities: list[str]) -> Optional[str]:
    """Mock never overrides the keyword classifier."""
    return None
