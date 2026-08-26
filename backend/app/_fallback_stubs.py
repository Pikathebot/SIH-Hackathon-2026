"""
Internal fallback AI stubs — used ONLY when ai_service mock imports fail.

These are contract-compliant stand-ins that live inside the backend module so
the backend can run independently during development, even if Person 1/2
haven't implemented their mock.py files yet.

Once ai_service/rsunivlm/mock.py and ai_service/fusion/mock.py are populated,
these stubs are automatically bypassed (the orchestrator prefers the real mocks).

Confidence scores use heuristic values and are labeled as such in meta.parameters
per AI_SERVICE_CONTRACT.md §2.
"""

import time

from ai_service.common.types import (
    VQAResult,
    CaptioningResult,
    DetectionResult,
    ChangeResult,
    FusionResult,
)

# ---------------------------------------------------------------------------
# Stub: RSUniVLM functions — AI_SERVICE_CONTRACT.md §2
# ---------------------------------------------------------------------------

def run_vqa(image, question: str) -> VQAResult:
    """Fallback VQA stub. Prompt tag: [VQA]. Simulated latency ~0.3s."""
    start = time.time()
    time.sleep(0.3)
    latency = int((time.time() - start) * 1000)
    return {
        "answer": (
            "Based on the satellite image analysis, the observed features include "
            "residential structures and vegetation coverage in the region."
        ),
        "confidence": 0.75,
        "meta": {
            "tool_used": "rsunivlm_vqa",
            "parameters": {
                "prompt_tag": "[VQA]",
                "confidence_source": "heuristic",
                "fallback_stub": True,
            },
            "latency_ms": latency,
        },
    }


def run_captioning(image) -> CaptioningResult:
    """Fallback captioning stub. Prompt tag: [CAP]. Simulated latency ~0.5s."""
    start = time.time()
    time.sleep(0.5)
    latency = int((time.time() - start) * 1000)
    return {
        "caption": (
            "An aerial satellite view showing a mix of urban development "
            "with residential buildings, road networks, and patches of "
            "green vegetation interspersed throughout the area."
        ),
        "confidence": 0.72,
        "meta": {
            "tool_used": "rsunivlm_cap",
            "parameters": {
                "prompt_tag": "[CAP]",
                "confidence_source": "heuristic",
                "fallback_stub": True,
            },
            "latency_ms": latency,
        },
    }


def run_detection(image, query: str, mode: str = "auto") -> DetectionResult:
    """
    Fallback detection stub.

    mode='auto' routing rule (AI_SERVICE_CONTRACT.md §2):
      - query contains where/locate/find/box → bbox (~0.4s)
      - query contains highlight/segment/mask → mask (~1.0s)
      - otherwise default to bbox
    """
    query_lower = query.lower()
    mask_keywords = {"highlight", "segment", "mask"}
    use_mask = mode == "mask" or (
        mode == "auto" and any(kw in query_lower for kw in mask_keywords)
    )

    start = time.time()
    if use_mask:
        time.sleep(1.0)  # simulate slow [SEG] path
        latency = int((time.time() - start) * 1000)
        return {
            "mode": "mask",
            "boxes": None,
            "mask_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==",
            "overlay_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
            "confidence": 0.70,
            "meta": {
                "tool_used": "rsunivlm_seg",
                "parameters": {
                    "prompt_tag": "[SEG]",
                    "confidence_source": "heuristic",
                    "fallback_stub": True,
                },
                "latency_ms": latency,
            },
        }
    else:
        time.sleep(0.4)  # simulate fast [VG] path
        latency = int((time.time() - start) * 1000)
        return {
            "mode": "bbox",
            "boxes": [[51, 384, 235, 506]],
            "mask_base64": None,
            "overlay_base64": None,
            "confidence": 0.82,
            "meta": {
                "tool_used": "rsunivlm_vg",
                "parameters": {
                    "prompt_tag": "[VG]",
                    "confidence_source": "heuristic",
                    "fallback_stub": True,
                },
                "latency_ms": latency,
            },
        }


def run_change_detection(image_before, image_after, query=None) -> ChangeResult:
    """Fallback change detection stub. Prompt tag: [CCD]. Simulated latency ~1.0s."""
    start = time.time()
    time.sleep(1.0)
    latency = int((time.time() - start) * 1000)
    return {
        "answer": (
            "Significant urban development detected — a new built-up area "
            "and parking lot have appeared in the northern section of the image."
        ),
        "mask_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==",
        "overlay_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
        "confidence": 0.78,
        "meta": {
            "tool_used": "rsunivlm_ccd",
            "parameters": {
                "prompt_tag": "[CCD]",
                "confidence_source": "heuristic",
                "fallback_stub": True,
            },
            "latency_ms": latency,
        },
    }


# ---------------------------------------------------------------------------
# Stub: Fusion function — AI_SERVICE_CONTRACT.md §3
# ---------------------------------------------------------------------------

def run_fusion(optical_image, sar_image, query: str) -> FusionResult:
    """Fallback fusion stub. Simulated latency ~0.8s."""
    start = time.time()
    time.sleep(0.8)
    latency = int((time.time() - start) * 1000)
    return {
        "answer": (
            "Multi-modal fusion analysis: the region shows approximately "
            "45% built-up area, 30% vegetation, and 25% water coverage. "
            "Urban development is concentrated in the eastern sector."
        ),
        "classified_regions_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==",
        "sar_only_reading": (
            "SAR backscatter analysis indicates high-reflectance surfaces "
            "consistent with metallic roofing and concrete structures in "
            "the eastern portion, with low-backscatter regions suggesting "
            "smooth water surfaces to the west."
        ),
        "confidence": 0.68,
        "meta": {
            "tool_used": "fusion_classifier",
            "parameters": {
                "confidence_source": "heuristic",
                "fallback_stub": True,
            },
            "latency_ms": latency,
        },
    }
