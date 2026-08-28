"""
Isolated unit test suite for RSUniVLM module functions.
Tests run_vqa, run_captioning, run_detection, run_change_detection,
and parsing utilities directly without requiring the backend router.
"""

import os
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

# Ensure project root is in sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from ai_service.common.errors import AIServiceError
from ai_service.rsunivlm.parsing import (
    parse_bounding_boxes,
    parse_segmentation_output,
    create_overlay_image,
    extract_water_spectral_mask,
)

# Test both mock and real wrappers depending on AI_SERVICE_MODE
AI_MODE = os.environ.get("AI_SERVICE_MODE", "mock")
if AI_MODE == "real":
    from ai_service.rsunivlm.wrapper import (
        run_vqa,
        run_captioning,
        run_detection,
        run_change_detection,
    )
else:
    from ai_service.rsunivlm.mock import (
        run_vqa,
        run_captioning,
        run_detection,
        run_change_detection,
    )


@pytest.fixture(autouse=True)
def set_fast_mock():
    os.environ["MOCK_FAST_MODE"] = "1"
    yield


@pytest.fixture
def sample_optical_image():
    """Create a synthetic RGB optical image with water, vegetation, and urban regions."""
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    # Water region (Blue dominant)
    arr[0:100, 0:100] = [20, 50, 200]
    # Vegetation region (Green dominant)
    arr[100:200, 100:200] = [30, 180, 40]
    # Urban region (Gray/Red)
    arr[200:256, 200:256] = [180, 180, 180]
    return Image.fromarray(arr, mode="RGB")


@pytest.fixture
def sample_pair_images():
    img_before = Image.new("RGB", (256, 256), color=(60, 120, 80))
    img_after = Image.new("RGB", (256, 256), color=(120, 60, 80))
    return img_before, img_after


# ── VQA Tests ────────────────────────────────────────────────────────────
class TestRSUniVLMVQA:
    def test_run_vqa_valid(self, sample_optical_image):
        result = run_vqa(sample_optical_image, "How many runways are visible?")
        assert isinstance(result, dict)
        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["meta"]["tool_used"] == "rsunivlm_vqa"
        assert result["meta"]["parameters"]["prompt_tag"] == "[VQA]"
        assert "confidence_source" in result["meta"]["parameters"]
        assert isinstance(result["meta"]["latency_ms"], int)

    def test_run_vqa_invalid_image_type(self):
        with pytest.raises(AIServiceError) as exc_info:
            run_vqa("not-an-image", "Where is the river?")  # type: ignore
        assert exc_info.value.code == "MODEL_INFERENCE_FAILED"


# ── Captioning Tests ─────────────────────────────────────────────────────
class TestRSUniVLMCaptioning:
    def test_run_captioning_valid(self, sample_optical_image):
        result = run_captioning(sample_optical_image)
        assert isinstance(result, dict)
        assert "caption" in result
        assert isinstance(result["caption"], str)
        assert len(result["caption"]) > 0
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["meta"]["tool_used"] == "rsunivlm_cap"
        assert result["meta"]["parameters"]["prompt_tag"] == "[CAP]"
        assert "confidence_source" in result["meta"]["parameters"]


# ── Detection Tests (Bbox, Mask, Auto) ────────────────────────────────────
class TestRSUniVLMDetection:
    def test_run_detection_bbox_mode(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Where is the aircraft?", mode="bbox")
        assert result["mode"] == "bbox"
        assert result["boxes"] is not None
        assert isinstance(result["boxes"], list)
        assert len(result["boxes"]) > 0
        for box in result["boxes"]:
            assert len(box) == 4
            assert all(isinstance(c, int) for c in box)
            x1, y1, x2, y2 = box
            assert 0 <= x1 <= x2 <= sample_optical_image.width
            assert 0 <= y1 <= y2 <= sample_optical_image.height
        assert result["mask_base64"] is None
        assert result["overlay_base64"] is None
        assert result["meta"]["tool_used"] == "rsunivlm_vg"

    def test_run_detection_mask_mode(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Segment the river water body", mode="mask")
        assert result["mode"] == "mask"
        assert result["boxes"] is None
        assert result["mask_base64"] is not None
        assert result["overlay_base64"] is not None
        assert isinstance(result["mask_base64"], str)
        assert result["meta"]["tool_used"] == "rsunivlm_seg"

    def test_run_detection_auto_routing_bbox(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Locate the building coordinates", mode="auto")
        assert result["mode"] == "bbox"
        assert result["meta"]["tool_used"] == "rsunivlm_vg"

    def test_run_detection_auto_routing_mask(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Highlight the flood inundation zone", mode="auto")
        assert result["mode"] == "mask"
        assert result["meta"]["tool_used"] == "rsunivlm_seg"

    def test_run_detection_auto_routing_coastline(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Detect coastal lines in this image", mode="auto")
        assert result["mode"] == "mask"
        assert result["meta"]["tool_used"] == "rsunivlm_seg"
        assert result["mask_base64"] is not None

    def test_run_detection_auto_routing_landmass(self, sample_optical_image):
        result = run_detection(sample_optical_image, "Detect landmass in this scene", mode="auto")
        assert result["mode"] == "mask"
        assert result["meta"]["tool_used"] == "rsunivlm_seg"
        assert result["mask_base64"] is not None


# ── Change Detection Tests ────────────────────────────────────────────────
class TestRSUniVLMChangeDetection:
    def test_run_change_detection_valid(self, sample_pair_images):
        img1, img2 = sample_pair_images
        result = run_change_detection(img1, img2, "Describe new buildings constructed")
        assert isinstance(result, dict)
        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["meta"]["tool_used"] == "rsunivlm_ccd"


# ── Parsing and Vision Utilities Tests ───────────────────────────────────
class TestVisionUtilities:
    def test_parse_bounding_boxes(self):
        text_with_box = "Found target object at [10, 20, 50, 60] with high certainty."
        boxes = parse_bounding_boxes(text_with_box, (100, 100))
        assert len(boxes) == 1
        assert boxes[0] == [10, 20, 50, 60]

    def test_extract_water_spectral_mask(self, sample_optical_image):
        mask = extract_water_spectral_mask(sample_optical_image)
        assert isinstance(mask, np.ndarray)
        assert mask.shape == (sample_optical_image.height, sample_optical_image.width)
        assert mask.dtype == np.uint8
        # The water region at (50, 50) should be detected
        assert mask[50, 50] == 255
        # The dry vegetation at (150, 150) should not be detected as water
        assert mask[150, 150] == 0

    def test_extract_coastline_contour(self, sample_optical_image):
        from ai_service.rsunivlm.parsing import extract_coastline_contour
        mask = extract_water_spectral_mask(sample_optical_image)
        contour = extract_coastline_contour(mask, thickness=2)
        assert isinstance(contour, np.ndarray)
        assert contour.shape == mask.shape
        assert np.count_nonzero(contour) > 0

    def test_create_overlay_image(self, sample_optical_image):
        mask = np.zeros((sample_optical_image.height, sample_optical_image.width), dtype=np.uint8)
        mask[20:80, 20:80] = 255
        overlay = create_overlay_image(sample_optical_image, mask, color=(0, 0, 255), alpha=0.5)
        assert isinstance(overlay, Image.Image)
        assert overlay.size == sample_optical_image.size

    def test_clean_vlm_text_output_strips_delimiters_and_loops(self):
        from ai_service.rsunivlm.parsing import clean_vlm_text_output
        raw = "the two scenes seem identical .### 2410 ### 2410 ### 2410 ### 2410 ### 2410"
        cleaned = clean_vlm_text_output(raw)
        assert cleaned == "the two scenes seem identical."

        leaked_tag = "[CCD] Major urban expansion observed on the east sector.<|im_end|>"
        assert clean_vlm_text_output(leaked_tag) == "Major urban expansion observed on the east sector."
