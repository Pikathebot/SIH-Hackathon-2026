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
from ai_service.common.errors import (
    AIServiceError,
    INVALID_MODALITY_COMBINATION,
    MODEL_INFERENCE_FAILED,
)
from ai_service.rsunivlm import mock as rsunivlm_mock
from ai_service.fusion import mock as fusion_mock

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


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def enable_fast_mock_mode():
    """Ensure fast tests in pytest runs while allowing realistic latencies in manual verification."""
    os.environ["MOCK_FAST_MODE"] = "1"
    yield
    os.environ.pop("MOCK_FAST_MODE", None)


@pytest.fixture
def sample_image():
    return Image.new("RGB", (256, 256), color=(73, 109, 137))


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


# ── Mock Implementation Conformance Tests ────────────────────────────

def test_mock_vqa(sample_image):
    result = rsunivlm_mock.run_vqa(sample_image, "How many basketball courts?")
    assert_vqa_result(result)


def test_mock_captioning(sample_image):
    result = rsunivlm_mock.run_captioning(sample_image)
    assert_captioning_result(result)


from unittest.mock import patch, MagicMock
from ai_service.rsunivlm.parsing import resolve_detection_mode


# ── Shared Detection Routing Logic Tests ──────────────────────────────

@pytest.mark.parametrize(
    "query, expected_mode",
    [
        # Precedence regression cases: localization actions beat subject keywords
        ("Where is the water body?", "bbox"),
        ("Locate the flooded coastal area", "bbox"),
        ("Find the urban built-up region", "bbox"),
        ("Where is the forest boundary?", "bbox"),
        ("Locate building coordinates", "bbox"),
        ("Find all ships in the harbor", "bbox"),
        ("Where is the aircraft runway?", "bbox"),
        ("Box the target object", "bbox"),
        # Mask / segmentation / continuous features without localization actions
        ("Highlight the water bodies in this image", "mask"),
        ("Segment the river network", "mask"),
        ("Detect coastal lines in this image", "mask"),
        ("Detect landmass in this scene", "mask"),
        ("Delineate the forest boundary", "mask"),
        ("Highlight flood inundation zones", "mask"),
        ("Map urban built-up coverage", "mask"),
        ("Show lake extent", "mask"),
        ("Detect shoreline", "mask"),
        # Default fast path (discrete targets without localization keywords)
        ("Detect airplanes", "bbox"),
        ("Count cargo ships", "bbox"),
        ("Identify vehicles", "bbox"),
    ],
)
def test_resolve_detection_mode_auto(query: str, expected_mode: str):
    """Direct unit tests for resolve_detection_mode per AI_SERVICE_CONTRACT.md §2."""
    assert resolve_detection_mode(query, mode="auto") == expected_mode


@pytest.mark.parametrize("explicit_mode", ["bbox", "mask"])
def test_resolve_detection_mode_explicit(explicit_mode: str):
    """Explicit mode overrides all query keyword heuristics."""
    assert resolve_detection_mode("Highlight water bodies", mode=explicit_mode) == explicit_mode
    assert resolve_detection_mode("Where is the aircraft?", mode=explicit_mode) == explicit_mode


def _run_detection_target(target: str, image: Image.Image, query: str, mode: str = "auto") -> dict:
    """Helper to execute run_detection against either rsunivlm.mock or rsunivlm.wrapper."""
    if target == "mock":
        return rsunivlm_mock.run_detection(image, query, mode=mode)
    elif target == "wrapper":
        from ai_service.rsunivlm.wrapper import run_detection as wrapper_run_detection
        with patch("ai_service.rsunivlm.wrapper._get_model", return_value=(MagicMock(), MagicMock(), MagicMock())):
            with patch("ai_service.rsunivlm.wrapper.run_raw_inference") as mock_infer:
                mock_infer.side_effect = lambda model, tokenizer, image_processor, images, message, max_new_tokens: (
                    ("Found target at [10, 20, 50, 60]", 50, 0.85)
                    if message.startswith("[VG]")
                    else ("others *10, water *20, others *546", 100, 0.90)
                )
                return wrapper_run_detection(image, query, mode=mode)
    raise ValueError(f"Unknown detection target: {target}")


@pytest.mark.parametrize("target", ["mock", "wrapper"])
def test_detection_auto_bbox(sample_image, target: str):
    # Where query -> auto routes to bbox
    result = _run_detection_target(target, sample_image, "Where is the aircraft?", mode="auto")
    assert_detection_result(result, expected_mode="bbox")
    assert result["boxes"] is not None
    assert result["mask_base64"] is None


@pytest.mark.parametrize("target", ["mock", "wrapper"])
def test_detection_auto_mask(sample_image, target: str):
    # Highlight query -> auto routes to mask
    result = _run_detection_target(target, sample_image, "Highlight the water bodies in this image", mode="auto")
    assert_detection_result(result, expected_mode="mask")
    assert result["boxes"] is None
    assert result["mask_base64"] is not None
    assert result["overlay_base64"] is not None


@pytest.mark.parametrize("target", ["mock", "wrapper"])
def test_detection_auto_where_beats_subject_keyword(sample_image, target: str):
    # Precedence: 'Where is the water body?' has 'where' which must beat 'water'
    result = _run_detection_target(target, sample_image, "Where is the water body?", mode="auto")
    assert_detection_result(result, expected_mode="bbox")
    assert result["boxes"] is not None
    assert result["mask_base64"] is None


@pytest.mark.parametrize("target", ["mock", "wrapper"])
def test_detection_explicit_modes(sample_image, target: str):
    bbox_res = _run_detection_target(target, sample_image, "arbitrary query", mode="bbox")
    assert_detection_result(bbox_res, expected_mode="bbox")

    mask_res = _run_detection_target(target, sample_image, "arbitrary query", mode="mask")
    assert_detection_result(mask_res, expected_mode="mask")


def test_mock_change_detection(sample_image):
    image_before = sample_image
    image_after = sample_image.copy()
    result = rsunivlm_mock.run_change_detection(
        image_before, image_after, query="What changed between these two dates?"
    )
    assert_change_result(result)


def test_mock_fusion(sample_image):
    optical_img = sample_image
    sar_img = Image.new("L", (256, 256), color=128).convert("RGB")
    optical_img._modality = "optical"
    sar_img._modality = "sar"

    result = fusion_mock.run_fusion(
        optical_img, sar_img, "Identify built-up and water-covered regions"
    )
    assert_fusion_result(result)


def test_mock_fusion_invalid_modality(sample_image):
    img1 = sample_image
    img2 = sample_image.copy()
    img1._modality = "optical"
    img2._modality = "optical"

    with pytest.raises(AIServiceError) as exc_info:
        fusion_mock.run_fusion(img1, img2, "Identify built-up areas")
    assert exc_info.value.code == INVALID_MODALITY_COMBINATION


def test_mock_invalid_inputs():
    with pytest.raises(AIServiceError) as exc_info:
        rsunivlm_mock.run_vqa(None, "Question?")  # type: ignore
    assert exc_info.value.code == MODEL_INFERENCE_FAILED


# ── Real Fusion Wrapper Conformance Tests ─────────────────────────────

def test_real_fusion_wrapper(sample_image):
    from ai_service.fusion.wrapper import run_fusion as real_run_fusion
    optical_img = sample_image
    sar_img = Image.new("L", (256, 256), color=128)
    optical_img._modality = "optical"
    sar_img._modality = "sar"

    result = real_run_fusion(optical_img, sar_img, "Identify land cover")
    assert_fusion_result(result)


def test_real_fusion_invalid_modality(sample_image):
    from ai_service.fusion.wrapper import run_fusion as real_run_fusion
    img1 = sample_image
    img2 = sample_image.copy()
    img1._modality = "sar"
    img2._modality = "sar"

    with pytest.raises(AIServiceError) as exc_info:
        real_run_fusion(img1, img2, "Identify built-up areas")
    assert exc_info.value.code == INVALID_MODALITY_COMBINATION
