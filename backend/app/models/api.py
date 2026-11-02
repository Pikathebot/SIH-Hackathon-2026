"""
Pydantic models for the HTTP API layer.

These match API_CONTRACT.md v2.0.0 exactly — field names are snake_case,
enum values come from CONTRACT.md §5.
"""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, model_validator


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ImageInput(BaseModel):
    """One image entry in a query request."""
    id: str
    modality: str = Field(..., pattern=r"^(optical|sar)$")
    date: Optional[str] = None          # ISO-8601 date string, optional
    url_or_base64: Optional[str] = None
    asset_id: Optional[str] = None      # v2.0.0: id from POST /api/v1/upload

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.url_or_base64) == bool(self.asset_id):
            raise ValueError("provide exactly one of url_or_base64 or asset_id")
        return self


class QueryRequest(BaseModel):
    """POST /api/v1/query request body — API_CONTRACT.md §1."""
    query: str = Field(..., min_length=1, max_length=2000)
    images: list[ImageInput] = Field(..., min_length=1, max_length=2)
    session_id: Optional[str] = None    # v2.0.0


class GeospatialMetadata(BaseModel):
    """Geospatial bounding coordinates and projection metadata."""
    crs: str = "EPSG:4326"
    image_bounds: list[float]  # [min_lon, min_lat, max_lon, max_lat] in WGS84
    secondary_image_bounds: Optional[list[float]] = None  # Secondary image WGS84 bounds for pairs
    geo_boxes: Optional[list[list[list[float]]]] = None  # [[[lon, lat], ...]]
    all_images_geo: Optional[list[dict]] = None


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
      UNSUPPORTED_FORMAT | MODEL_INFERENCE_FAILED | INTERNAL_ERROR | UNAUTHORIZED |
      FORBIDDEN | NOT_FOUND | CONFLICT | VALIDATION_ERROR | PAYLOAD_TOO_LARGE |
      QUOTA_EXCEEDED | RATE_LIMITED | QUEUE_FULL | INFERENCE_TIMEOUT
    """
    code: str
    message: str
    detail: Optional[str] = None
    request_id: Optional[str] = None  # v2.3.0: same value as the X-Request-ID header


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
    # Additive (API_CONTRACT v1.2): active engine + model-server reachability
    engine: Optional[dict] = None
    # Additive (API_CONTRACT v2.3.0)
    database: Optional[bool] = None
    queue: Optional[dict] = None
    gpu: Optional[dict] = None


# ---------------------------------------------------------------------------
# Auth, sessions and history — API_CONTRACT.md §5 (v2.0.0)
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=10, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class SessionCreate(BaseModel):
    title: str = Field(default="New analysis", min_length=1, max_length=200)


class SessionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    query_count: int = 0


class HistoryImage(BaseModel):
    asset_id: str
    modality: Optional[str] = None
    date: Optional[str] = None


class HistoryEntry(BaseModel):
    id: str
    query_text: str
    created_at: str
    status: str
    error_code: Optional[str] = None
    image_asset_ids: list[str]
    images: list[HistoryImage] = []  # v2.2.0
    response: Optional[QueryResponse] = None
