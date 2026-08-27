"""
Pydantic models for the HTTP API layer.

These match API_CONTRACT.md v1.0.0 exactly — field names are snake_case,
enum values come from CONTRACT.md §5.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ImageInput(BaseModel):
    """One image entry in a query request."""
    id: str
    modality: str = Field(..., pattern=r"^(optical|sar)$")
    date: Optional[str] = None          # ISO-8601 date string, optional
    url_or_base64: str


class QueryRequest(BaseModel):
    """POST /api/v1/query request body — API_CONTRACT.md §1."""
    query: str = Field(..., min_length=1, max_length=2000)
    images: list[ImageInput] = Field(..., min_length=1, max_length=2)


class GeospatialMetadata(BaseModel):
    """Geospatial bounding coordinates and projection metadata."""
    crs: str = "EPSG:4326"
    image_bounds: list[float]  # [min_lon, min_lat, max_lon, max_lat] in WGS84
    geo_boxes: Optional[list[list[list[float]]]] = None  # [[[lon, lat], ...]]


class VisualEvidence(BaseModel):
    """Visual evidence block in query response."""
    type: str                                       # "none" | "bbox" | "mask"
    boxes: Optional[list[list[int]]] = None         # [[x1,y1,x2,y2], ...]
    mask_base64: Optional[str] = None
    overlay_base64: Optional[str] = None
    geospatial: Optional[GeospatialMetadata] = None


class ExecutionSummary(BaseModel):
    """
    Execution trace — always present in every response, per API_CONTRACT.md §1.

    This is the field the frontend renders in the "execution trace panel".
    It is a required demo feature, not decoration.
    """
    selected_task: str
    tool_used: str
    parameters: dict
    inputs_validated: bool
    latency_ms: int


class QueryResponse(BaseModel):
    """POST /api/v1/query 200 OK response body — API_CONTRACT.md §1."""
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    task: str
    visual_evidence: VisualEvidence
    execution_summary: ExecutionSummary


# ---------------------------------------------------------------------------
# Error models
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    """
    Error detail block — API_CONTRACT.md §1 error shape.

    code is one of:
      INVALID_IMAGE_COUNT | INVALID_MODALITY_COMBINATION |
      UNSUPPORTED_FORMAT | MODEL_INFERENCE_FAILED | INTERNAL_ERROR
    """
    code: str
    message: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    """Wrapper for all error responses — always returns this JSON shape."""
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    """GET /api/v1/health response — API_CONTRACT.md §1."""
    status: str = "ok"
    rsunivlm_loaded: bool
    fusion_loaded: bool
