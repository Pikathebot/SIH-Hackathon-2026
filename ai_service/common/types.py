from typing import TypedDict, Literal, Optional

Modality = Literal["optical", "sar"]

class ExecutionMeta(TypedDict):
    tool_used: str          # canonical value from CONTRACT.md §5, e.g. "rsunivlm_vqa"
    parameters: dict        # opaque per-tool params, e.g. {"prompt_tag": "[VQA]"}
    latency_ms: int

class VQAResult(TypedDict):
    answer: str
    confidence: float       # 0.0-1.0
    meta: ExecutionMeta

class CaptioningResult(TypedDict):
    caption: str
    confidence: float
    meta: ExecutionMeta

class DetectionResult(TypedDict):
    mode: Literal["bbox", "mask"]
    boxes: Optional[list[list[int]]]      # [[x1,y1,x2,y2], ...], present iff mode == "bbox"
    mask_base64: Optional[str]            # present iff mode == "mask"
    overlay_base64: Optional[str]         # present iff mode == "mask"
    confidence: float
    meta: ExecutionMeta

class ChangeResult(TypedDict):
    answer: str
    mask_base64: Optional[str]
    overlay_base64: Optional[str]
    confidence: float
    meta: ExecutionMeta

class FusionResult(TypedDict):
    answer: str
    classified_regions_base64: str
    sar_only_reading: str            # required — the standalone SAR interpretation, not just a fused answer
    confidence: float
    meta: ExecutionMeta
