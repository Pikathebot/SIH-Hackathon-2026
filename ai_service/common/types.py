"""
Shared types for SatQuery AI service layer.

Defined once here, imported by all modules — per AI_SERVICE_CONTRACT.md §1 v1.0.0.
Do not redefine these locally in any module.
"""

from typing import TypedDict, Literal, Optional


# ---------------------------------------------------------------------------
# Canonical type aliases — CONTRACT.md §5
# ---------------------------------------------------------------------------
Modality = Literal["optical", "sar"]


# ---------------------------------------------------------------------------
# Execution metadata — included in every AI result
# ---------------------------------------------------------------------------
class ExecutionMeta(TypedDict):
    """Metadata about how the AI function executed."""
    tool_used: str          # canonical value from CONTRACT.md §5, e.g. "rsunivlm_vqa"
    parameters: dict        # opaque per-tool params, e.g. {"prompt_tag": "[VQA]"}
    latency_ms: int         # wall-clock model execution time in milliseconds


# ---------------------------------------------------------------------------
# RSUniVLM result types — AI_SERVICE_CONTRACT.md §2
# ---------------------------------------------------------------------------
class VQAResult(TypedDict):
    """Return type for run_vqa()."""
    answer: str
    confidence: float       # 0.0-1.0
    meta: ExecutionMeta


class CaptioningResult(TypedDict):
    """Return type for run_captioning()."""
    caption: str
    confidence: float       # 0.0-1.0
    meta: ExecutionMeta


class DetectionResult(TypedDict):
    """Return type for run_detection()."""
    mode: Literal["bbox", "mask"]
    boxes: Optional[list[list[int]]]      # [[x1,y1,x2,y2], ...], present iff mode == "bbox"
    mask_base64: Optional[str]            # present iff mode == "mask"
    overlay_base64: Optional[str]         # present iff mode == "mask"
    confidence: float
    meta: ExecutionMeta


class ChangeResult(TypedDict):
    """Return type for run_change_detection()."""
    answer: str
    mask_base64: Optional[str]
    overlay_base64: Optional[str]
    confidence: float
    meta: ExecutionMeta


# ---------------------------------------------------------------------------
# Fusion result type — AI_SERVICE_CONTRACT.md §3
# ---------------------------------------------------------------------------
class FusionResult(TypedDict):
    """Return type for run_fusion()."""
    answer: str
    classified_regions_base64: str        # base64 encoded classified regions overlay
    sar_only_reading: str                 # standalone SAR-only interpretation
    confidence: float
    meta: ExecutionMeta
