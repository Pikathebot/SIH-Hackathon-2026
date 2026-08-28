"""
Isolated unit test suite for Optical-SAR Fusion module functions.
Tests run_fusion, independent SAR interpretation, modality validation,
and classification metrics directly without requiring the backend router.
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

from ai_service.common.errors import (
    AIServiceError,
    INVALID_MODALITY_COMBINATION,
    MODEL_INFERENCE_FAILED,
)

# Test both mock and real wrappers depending on AI_SERVICE_MODE
AI_MODE = os.environ.get("AI_SERVICE_MODE", "mock")
if AI_MODE == "real":
    from ai_service.fusion.wrapper import run_fusion
else:
    from ai_service.fusion.mock import run_fusion


@pytest.fixture(autouse=True)
def set_fast_mock():
    os.environ["MOCK_FAST_MODE"] = "1"
    yield


@pytest.fixture
def optical_image():
    """Synthetic optical image with distinct blue water, green veg, and gray urban."""
    arr = np.zeros((256, 256, 3), dtype=np.uint8)
    arr[0:80, :] = [20, 80, 220]    # Water
    arr[80:180, :] = [30, 160, 40]  # Vegetation
    arr[180:256, :] = [200, 200, 200]  # Urban
    img = Image.fromarray(arr, mode="RGB")
    img._modality = "optical"
    return img


@pytest.fixture
def sar_image():
    """Synthetic SAR image with low specular water, medium veg, and high urban backscatter."""
    arr = np.zeros((256, 256), dtype=np.uint8)
    arr[0:80, :] = 25     # Specular low backscatter (< 0.20 normalized)
    arr[80:180, :] = 100  # Volume scatter (0.39 normalized)
    arr[180:256, :] = 220 # Double-bounce reflector (0.86 normalized)
    img = Image.fromarray(arr, mode="L")
    img._modality = "sar"
    return img


class TestOpticalSARFusion:
    def test_run_fusion_valid_pair(self, optical_image, sar_image):
        result = run_fusion(
            optical_image,
            sar_image,
            "Analyze urban infrastructure and water bodies",
        )
        assert isinstance(result, dict)
        assert "answer" in result
        assert isinstance(result["answer"], str) and len(result["answer"]) > 0

        assert "classified_regions_base64" in result
        assert isinstance(result["classified_regions_base64"], str)
        assert len(result["classified_regions_base64"]) > 50

        # sar_only_reading must be genuine and independent
        assert "sar_only_reading" in result
        assert isinstance(result["sar_only_reading"], str)
        assert len(result["sar_only_reading"]) > 20
        assert result["sar_only_reading"] != result["answer"], "sar_only_reading must not merely duplicate answer"

        # Confidence bounds and source
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

        # Meta validation
        meta = result["meta"]
        assert meta["tool_used"] == "fusion_classifier"
        assert isinstance(meta["latency_ms"], int)
        assert meta["latency_ms"] >= 0
        assert "parameters" in meta
        params = meta["parameters"]
        assert "urban_coverage_pct" in params
        assert "vegetation_coverage_pct" in params
        assert "water_coverage_pct" in params
        assert "confidence_source" in params

    def test_sar_water_specular_agreement(self, optical_image, sar_image):
        """Verify that fused water coverage correctly accounts for specular low backscatter."""
        result = run_fusion(optical_image, sar_image, "Segment water and rivers")
        water_pct = result["meta"]["parameters"]["water_coverage_pct"]
        # Water was created on top ~31% of image (80/256)
        assert 20.0 <= water_pct <= 45.0

    def test_invalid_image_type_raises_service_error(self, optical_image):
        with pytest.raises(AIServiceError) as exc:
            run_fusion(optical_image, "not-a-pil-image", "query")  # type: ignore
        assert exc.value.code == MODEL_INFERENCE_FAILED

    def test_modality_mismatch_two_sar_rejected(self, sar_image):
        sar2 = sar_image.copy()
        sar2._modality = "sar"
        with pytest.raises(AIServiceError) as exc:
            run_fusion(sar_image, sar2, "fusion query")
        assert exc.value.code == INVALID_MODALITY_COMBINATION

    def test_modality_mismatch_two_optical_rejected(self, optical_image):
        opt2 = optical_image.copy()
        opt2._modality = "optical"
        with pytest.raises(AIServiceError) as exc:
            run_fusion(optical_image, opt2, "fusion query")
        assert exc.value.code == INVALID_MODALITY_COMBINATION
