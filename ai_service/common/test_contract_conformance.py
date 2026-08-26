"""
Conformance test suite for AI Service module contracts.
Validates both mock.py and wrapper.py against AI_SERVICE_CONTRACT.md v1.0.0.
"""

import os
import pytest
from PIL import Image

from ai_service.common.types import (
    VQAResult,
    CaptioningResult,
    DetectionResult,
    ChangeResult,
    FusionResult,
    ExecutionMeta,
)
from ai_service.common.errors import AIServiceError

# Canonical values from CONTRACT.md §5
CANONICAL_TOOLS = {
    "rsunivlm_vqa",
    "rsunivlm_cap",
    "rsunivlm_vg",
    "rsunivlm_seg",
    "rsunivlm_ccd",
    "fusion_classifier",
}


def assert_execution_meta(meta: dict, expected_tool: str = None):
    assert isinstance(meta, dict), "meta must be a dict"
    assert "tool_used" in meta, "meta must include 'tool_used'"
    assert "parameters" in meta, "meta must include 'parameters'"
    assert "latency_ms" in meta, "meta must include 'latency_ms'"

    assert meta["tool_used"] in CANONICAL_TOOLS, f"Invalid tool_used: {meta['tool_used']}"
    if expected_tool:
        assert meta["tool_used"] == expected_tool, f"Expected tool {expected_tool}, got {meta['tool_used']}"

    assert isinstance(meta["parameters"], dict), "parameters must be a dict"
    assert isinstance(meta["latency_ms"], int), "latency_ms must be an int"
    assert meta["latency_ms"] >= 0, "latency_ms must be non-negative"


def assert_confidence(conf: float):
    assert isinstance(conf, (float, int)), f"confidence must be float, got {type(conf)}"
    assert 0.0 <= conf <= 1.0, f"confidence must be between 0.0 and 1.0, got {conf}"


def assert_vqa_result(res: dict):
    assert isinstance(res, dict)
    assert "answer" in res and isinstance(res["answer"], str) and len(res["answer"]) > 0
    assert "confidence" in res
    assert_confidence(res["confidence"])
    assert "meta" in res
    assert_execution_meta(res["meta"], expected_tool="rsunivlm_vqa")


def assert_captioning_result(res: dict):
    assert isinstance(res, dict)
    assert "caption" in res and isinstance(res["caption"], str) and len(res["caption"]) > 0
    assert "confidence" in res
    assert_confidence(res["confidence"])
    assert "meta" in res
    assert_execution_meta(res["meta"], expected_tool="rsunivlm_cap")


def assert_detection_result(res: dict, expected_mode: str = None):
    assert isinstance(res, dict)
    assert "mode" in res
    assert res["mode"] in ("bbox", "mask")
    if expected_mode:
        assert res["mode"] == expected_mode

    assert "confidence" in res
    assert_confidence(res["confidence"])
    assert "meta" in res

    if res["mode"] == "bbox":
        assert_execution_meta(res["meta"], expected_tool="rsunivlm_vg")
        assert "boxes" in res
        assert isinstance(res["boxes"], list)
        assert len(res["boxes"]) > 0
        for box in res["boxes"]:
            assert isinstance(box, list)
            assert len(box) == 4
            assert all(isinstance(c, int) for c in box)
    elif res["mode"] == "mask":
        assert_execution_meta(res["meta"], expected_tool="rsunivlm_seg")
        assert "mask_base64" in res
        assert res["mask_base64"] is not None
        assert "overlay_base64" in res
        assert res["overlay_base64"] is not None


def assert_change_result(res: dict):
    assert isinstance(res, dict)
    assert "answer" in res and isinstance(res["answer"], str) and len(res["answer"]) > 0
    assert "confidence" in res
    assert_confidence(res["confidence"])
    assert "meta" in res
    assert_execution_meta(res["meta"], expected_tool="rsunivlm_ccd")


def assert_fusion_result(res: dict):
    assert isinstance(res, dict)
    assert "answer" in res and isinstance(res["answer"], str) and len(res["answer"]) > 0
    assert "classified_regions_base64" in res and isinstance(res["classified_regions_base64"], str)
    assert "sar_only_reading" in res and isinstance(res["sar_only_reading"], str) and len(res["sar_only_reading"]) > 0
    # Must be genuine standalone SAR reading, not copy of answer
    assert res["sar_only_reading"] != res["answer"], "sar_only_reading must not simply mirror answer"
    assert "confidence" in res
    assert_confidence(res["confidence"])
    assert "meta" in res
    assert_execution_meta(res["meta"], expected_tool="fusion_classifier")


# ── Structural tests for Types & Errors ──────────────────────────────

def test_types_and_errors_definitions():
    """Verify that all typed dicts and exception classes can be instantiated."""
    err = AIServiceError(code="MODEL_INFERENCE_FAILED", message="Inference timed out", detail="CUDA OOM")
    assert err.code == "MODEL_INFERENCE_FAILED"
    assert err.message == "Inference timed out"
    assert "MODEL_INFERENCE_FAILED" in str(err)

    meta: ExecutionMeta = {
        "tool_used": "rsunivlm_vqa",
        "parameters": {"prompt_tag": "[VQA]"},
        "latency_ms": 420,
    }
    assert_execution_meta(meta, expected_tool="rsunivlm_vqa")
