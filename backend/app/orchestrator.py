"""
Orchestrator — the core brain of the SatQuery AI backend.

Responsibilities per AI_SERVICE_CONTRACT.md §4 (Person 3, not delegated):
  1. Input validation (image count, modality match per task)
  2. Intent classification (query text → canonical task)
  3. Base64/URL decode → PIL.Image at the API boundary
  4. AI function dispatch (mock or real, via AI_SERVICE_MODE)
  5. Response assembly (AI result TypedDict → API QueryResponse)
  6. DB audit logging (non-blocking — failure never breaks the response)
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from PIL import Image

from app.config import AI_SERVICE_MODE
from app.geotiff import (
    GeoMetadata,
    is_geotiff,
    pixel_boxes_to_geo_polygons,
    process_geotiff,
)
from app.models.api import (
    ExecutionSummary,
    GeospatialMetadata,
    QueryRequest,
    QueryResponse,
    VisualEvidence,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AI service import — mock or real, per AI_SERVICE_MODE env var
# Graceful fallback to internal stubs if ai_service modules aren't ready.
# ---------------------------------------------------------------------------
_rsunivlm_loaded = False
_fusion_loaded = False

_run_vqa = None
_run_captioning = None
_run_detection = None
_run_change_detection = None
_run_fusion = None

# Try importing the contracted AI service modules first
try:
    if AI_SERVICE_MODE == "real":
        from ai_service.rsunivlm.wrapper import (
            run_captioning as _ext_cap,
            run_change_detection as _ext_cd,
            run_detection as _ext_det,
            run_vqa as _ext_vqa,
        )
    else:
        from ai_service.rsunivlm.mock import (
            run_captioning as _ext_cap,
            run_change_detection as _ext_cd,
            run_detection as _ext_det,
            run_vqa as _ext_vqa,
        )
    _run_vqa = _ext_vqa
    _run_captioning = _ext_cap
    _run_detection = _ext_det
    _run_change_detection = _ext_cd
    _rsunivlm_loaded = True
    logger.info("RSUniVLM module loaded (mode=%s)", AI_SERVICE_MODE)
except (ImportError, AttributeError) as exc:
    logger.warning("RSUniVLM import failed (%s), using fallback stubs", exc)

try:
    if AI_SERVICE_MODE == "real":
        from ai_service.fusion.wrapper import run_fusion as _ext_fusion
    else:
        from ai_service.fusion.mock import run_fusion as _ext_fusion
    _run_fusion = _ext_fusion
    _fusion_loaded = True
    logger.info("Fusion module loaded (mode=%s)", AI_SERVICE_MODE)
except (ImportError, AttributeError) as exc:
    logger.warning("Fusion import failed (%s), using fallback stubs", exc)

# Fall back to internal stubs if external modules aren't available
if not _rsunivlm_loaded:
    from app._fallback_stubs import (
        run_captioning as _fb_cap,
        run_change_detection as _fb_cd,
        run_detection as _fb_det,
        run_vqa as _fb_vqa,
    )
    _run_vqa = _fb_vqa
    _run_captioning = _fb_cap
    _run_detection = _fb_det
    _run_change_detection = _fb_cd
    _rsunivlm_loaded = True  # stubs are available
    logger.info("Using fallback RSUniVLM stubs")

if not _fusion_loaded:
    from app._fallback_stubs import run_fusion as _fb_fusion
    _run_fusion = _fb_fusion
    _fusion_loaded = True  # stubs are available
    logger.info("Using fallback Fusion stubs")


def is_rsunivlm_loaded() -> bool:
    """Check whether the RSUniVLM module (or fallback) is available."""
    return _rsunivlm_loaded


def is_fusion_loaded() -> bool:
    """Check whether the Fusion module (or fallback) is available."""
    return _fusion_loaded


# ---------------------------------------------------------------------------
# Validation error — internal, mapped to HTTP 400 by the router
# ---------------------------------------------------------------------------
class QueryValidationError(Exception):
    """Raised when input validation fails. Maps to HTTP 400."""

    def __init__(self, code: str, message: str, detail: Optional[str] = None) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)


# ---------------------------------------------------------------------------
# Input validation — per API_CONTRACT.md §1 constraints
# ---------------------------------------------------------------------------
def validate_inputs(request: QueryRequest) -> None:
    """
    Validate image count and modality combinations.

    The backend owns all validation — never trust the frontend to have
    pre-validated (API_CONTRACT.md §4).
    """
    images = request.images

    # Image count: must be 1 or 2
    if len(images) < 1 or len(images) > 2:
        raise QueryValidationError(
            code="INVALID_IMAGE_COUNT",
            message=f"Expected 1 or 2 images, got {len(images)}.",
            detail="The images array must contain 1 or 2 entries.",
        )

    # Modality validation
    for img in images:
        if img.modality not in ("optical", "sar"):
            raise QueryValidationError(
                code="INVALID_MODALITY_COMBINATION",
                message=f"Unsupported modality: '{img.modality}'. Must be 'optical' or 'sar'.",
            )

    # Two-image combination checks
    if len(images) == 2:
        modalities = sorted(img.modality for img in images)

        if modalities == ["optical", "optical"]:
            # Change detection: both must have dates that differ
            dates = [img.date for img in images]
            if not all(dates):
                raise QueryValidationError(
                    code="INVALID_MODALITY_COMBINATION",
                    message="Change detection requires both images to have a 'date' field.",
                )
            if dates[0] == dates[1]:
                raise QueryValidationError(
                    code="INVALID_MODALITY_COMBINATION",
                    message="Change detection requires images with different dates.",
                )
        elif modalities == ["optical", "sar"]:
            pass  # Fusion — valid combination
        elif modalities == ["sar", "sar"]:
            raise QueryValidationError(
                code="INVALID_MODALITY_COMBINATION",
                message=(
                    "Two SAR images are not a valid combination. "
                    "Provide 2 optical (change detection) or 1 optical + 1 SAR (fusion)."
                ),
            )


# ---------------------------------------------------------------------------
# Intent classification — orchestrator's job, not the AI modules'
# ---------------------------------------------------------------------------
_DETECTION_KEYWORDS = frozenset({
    "where", "locate", "find", "box",
    "highlight", "segment", "mask",
    "detect", "identify", "show",
})

_CAPTIONING_KEYWORDS = frozenset({
    "caption", "describe", "description",
    "what is this", "what do you see",
    "summarize", "summarise", "overview",
})


def classify_intent(request: QueryRequest) -> str:
    """
    Classify query intent → one of the canonical task values.

    Values from CONTRACT.md §5: vqa | captioning | detection | change_detection | fusion
    """
    images = request.images
    query_lower = request.query.lower()
    modalities = sorted(img.modality for img in images)

    # Two-image tasks are determined purely by modality combination
    if len(images) == 2:
        if modalities == ["optical", "optical"]:
            return "change_detection"
        if modalities == ["optical", "sar"]:
            return "fusion"

    # Single-image: disambiguate by query text
    # Check detection keywords
    if any(kw in query_lower for kw in _DETECTION_KEYWORDS):
        return "detection"

    # Check captioning keywords
    if any(kw in query_lower for kw in _CAPTIONING_KEYWORDS):
        return "captioning"

    # Default: VQA
    return "vqa"


# ---------------------------------------------------------------------------
# Image decoding — base64/URL → PIL.Image at the API boundary
# AI modules work with PIL.Image.Image objects, never raw base64.
# ---------------------------------------------------------------------------
def _decode_image(url_or_base64: str) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    """Decode a base64 string or URL to a PIL Image and optional GeoMetadata."""
    data = url_or_base64.strip()

    # Handle data URI scheme (e.g. "data:image/png;base64,iVBOR...")
    if data.startswith("data:"):
        _, _, after_comma = data.partition(",")
        data = after_comma

    # Try base64 decode
    try:
        image_bytes = base64.b64decode(data)
        if is_geotiff(image_bytes):
            return process_geotiff(image_bytes)
        return Image.open(io.BytesIO(image_bytes)).convert("RGB"), None
    except Exception:
        pass

    # Try URL
    if data.startswith(("http://", "https://")):
        try:
            import httpx
            response = httpx.get(data, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            image_bytes = response.content
            if is_geotiff(image_bytes):
                return process_geotiff(image_bytes)
            return Image.open(io.BytesIO(image_bytes)).convert("RGB"), None
        except Exception as exc:
            raise QueryValidationError(
                code="UNSUPPORTED_FORMAT",
                message=f"Failed to download image from URL: {exc}",
            ) from exc

    raise QueryValidationError(
        code="UNSUPPORTED_FORMAT",
        message="Could not decode image. Provide a valid base64 string or HTTPS URL.",
    )


def _compute_image_checksum(image: Image.Image) -> str:
    """Compute SHA-256 checksum of an image's raw bytes."""
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()


# ---------------------------------------------------------------------------
# AI dispatch — calls the correct function in a thread pool
# (AI functions are sync per AI_SERVICE_CONTRACT.md)
# ---------------------------------------------------------------------------
def _dispatch_ai_sync(
    task: str,
    request: QueryRequest,
    decoded_images: list[Image.Image],
) -> dict:
    """
    Synchronous dispatch — runs in a thread pool via asyncio.to_thread().

    Returns the raw TypedDict result from the AI function.
    """
    if task == "vqa":
        return _run_vqa(decoded_images[0], request.query)

    elif task == "captioning":
        return _run_captioning(decoded_images[0])

    elif task == "detection":
        return _run_detection(decoded_images[0], request.query)

    elif task == "change_detection":
        # Sort by date so earlier image = before, later = after
        img_pairs = list(zip(request.images, decoded_images))
        img_pairs.sort(key=lambda pair: pair[0].date or "")
        return _run_change_detection(
            img_pairs[0][1],
            img_pairs[1][1],
            request.query,
        )

    elif task == "fusion":
        # Separate optical and SAR images
        optical_img = None
        sar_img = None
        for img_input, decoded in zip(request.images, decoded_images):
            decoded._modality = img_input.modality
            if img_input.modality == "optical":
                optical_img = decoded
            else:
                sar_img = decoded
        return _run_fusion(optical_img, sar_img, request.query)

    else:
        raise ValueError(f"Unknown task: {task}")


# ---------------------------------------------------------------------------
# Response assemblers — AI result TypedDict → API QueryResponse
# ---------------------------------------------------------------------------
def _assemble_response(
    task: str,
    result: dict,
    geo_meta: Optional[GeoMetadata] = None,
    secondary_geo_meta: Optional[GeoMetadata] = None,
) -> QueryResponse:
    """Map an AI result dict to the API response shape with optional GeoTIFF coordinates."""
    meta = result["meta"]
    execution_summary = ExecutionSummary(
        selected_task=task,
        tool_used=meta["tool_used"],
        parameters=meta["parameters"],
        inputs_validated=True,
        latency_ms=meta["latency_ms"],
    )

    geospatial = None
    if geo_meta and geo_meta.image_bounds:
        boxes = result.get("boxes")
        geo_boxes = pixel_boxes_to_geo_polygons(boxes, geo_meta) if boxes else None

        all_geo = [{"crs": geo_meta.crs, "bounds": geo_meta.image_bounds}]
        sec_bounds = None
        if secondary_geo_meta and secondary_geo_meta.image_bounds:
            sec_bounds = secondary_geo_meta.image_bounds
            all_geo.append({"crs": secondary_geo_meta.crs, "bounds": secondary_geo_meta.image_bounds})

        geospatial = GeospatialMetadata(
            crs=geo_meta.crs,
            image_bounds=geo_meta.image_bounds,
            secondary_image_bounds=sec_bounds,
            geo_boxes=geo_boxes,
            all_images_geo=all_geo if len(all_geo) > 1 else None,
        )

    if task == "vqa":
        return QueryResponse(
            answer=result["answer"],
            confidence=result["confidence"],
            task=task,
            visual_evidence=VisualEvidence(type="none", geospatial=geospatial),
            execution_summary=execution_summary,
        )

    elif task == "captioning":
        return QueryResponse(
            answer=result["caption"],
            confidence=result["confidence"],
            task=task,
            visual_evidence=VisualEvidence(type="none", geospatial=geospatial),
            execution_summary=execution_summary,
        )

    elif task == "detection":
        ve_type = result["mode"]  # "bbox" or "mask"
        answer = (
            f"Detection completed with {len(result.get('boxes') or [])} region(s) found."
            if ve_type == "bbox"
            else "Segmentation mask generated successfully."
        )
        return QueryResponse(
            answer=answer,
            confidence=result["confidence"],
            task=task,
            visual_evidence=VisualEvidence(
                type=ve_type,
                boxes=result.get("boxes"),
                mask_base64=result.get("mask_base64"),
                overlay_base64=result.get("overlay_base64"),
                geospatial=geospatial,
            ),
            execution_summary=execution_summary,
        )

    elif task == "change_detection":
        has_mask = result.get("mask_base64") is not None
        return QueryResponse(
            answer=result["answer"],
            confidence=result["confidence"],
            task=task,
            visual_evidence=VisualEvidence(
                type="mask" if has_mask else "none",
                mask_base64=result.get("mask_base64"),
                overlay_base64=result.get("overlay_base64"),
                geospatial=geospatial,
            ),
            execution_summary=execution_summary,
        )

    elif task == "fusion":
        return QueryResponse(
            answer=result["answer"],
            confidence=result["confidence"],
            task=task,
            visual_evidence=VisualEvidence(
                type="mask",
                mask_base64=result.get("classified_regions_base64"),
                overlay_base64=result.get("classified_regions_base64"),
                geospatial=geospatial,
            ),
            execution_summary=execution_summary,
        )

    else:
        raise ValueError(f"Unknown task for response assembly: {task}")


# ---------------------------------------------------------------------------
# DB audit logging — non-blocking, failure never breaks the response
# ---------------------------------------------------------------------------
async def _log_query_to_db(
    request: QueryRequest,
    task: str,
    response: QueryResponse,
    image_checksums: list[str],
) -> None:
    """
    Log the query and images to the SQLite database.

    This is best-effort — if it fails, we log the error but do not
    let it affect the API response. Per DATABASE_CONTRACT.md, persistence
    is not required for the core demo to function.
    """
    try:
        from app.database import get_db

        query_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        db = await get_db()
        try:
            # Insert image rows
            image_ids = []
            for img_input, checksum in zip(request.images, image_checksums):
                image_id = str(uuid.uuid4())
                image_ids.append(image_id)
                await db.execute(
                    """
                    INSERT INTO images (id, modality, capture_date, storage_path, checksum, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        image_id,
                        img_input.modality,
                        img_input.date,
                        f"images/{image_id}.png",  # placeholder path
                        checksum,
                        now,
                    ),
                )

            # Insert query row
            es = response.execution_summary
            ve = response.visual_evidence
            await db.execute(
                """
                INSERT INTO queries (
                    id, query_text, image_ids, selected_task, tool_used,
                    parameters, answer, confidence, visual_evidence_type,
                    visual_evidence_ref, latency_ms, inputs_validated,
                    status, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    request.query,
                    json.dumps(image_ids),
                    es.selected_task,
                    es.tool_used,
                    json.dumps(es.parameters),
                    response.answer,
                    response.confidence,
                    ve.type,
                    None,  # visual_evidence_ref — not persisting overlays to disk for now
                    es.latency_ms,
                    1,  # inputs_validated = True
                    "success",
                    None,
                    now,
                ),
            )
            await db.commit()
            logger.info("Query logged to DB: %s", query_id)
        finally:
            await db.close()

    except Exception:
        logger.exception("Failed to log query to DB (non-critical)")


# ---------------------------------------------------------------------------
# Main entry point — called by the router
# ---------------------------------------------------------------------------
async def process_query(request: QueryRequest) -> QueryResponse:
    """
    Full orchestrator pipeline:
    validate → classify → decode → dispatch AI → assemble response → log to DB.
    """
    # 1. Validate inputs
    validate_inputs(request)

    # 2. Classify intent
    task = classify_intent(request)

    # 3. Decode images (sync — fast operation)
    decoded_pairs = [_decode_image(img.url_or_base64) for img in request.images]
    decoded_images = [pair[0] for pair in decoded_pairs]
    
    # Extract geospatial metadata for all available images
    primary_geo_meta = None
    secondary_geo_meta = None
    if len(decoded_pairs) == 1:
        primary_geo_meta = decoded_pairs[0][1]
    elif len(decoded_pairs) >= 2:
        geo0 = decoded_pairs[0][1]
        geo1 = decoded_pairs[1][1]
        if geo0 and geo1:
            primary_geo_meta = geo0
            secondary_geo_meta = geo1
        elif geo0:
            primary_geo_meta = geo0
        elif geo1:
            primary_geo_meta = geo1

    # 4. Compute checksums for DB logging
    image_checksums = [_compute_image_checksum(img) for img in decoded_images]

    # 5. Dispatch to AI function (sync functions → run in thread pool)
    from ai_service.common.errors import AIServiceError
    try:
        result = await asyncio.to_thread(
            _dispatch_ai_sync, task, request, decoded_images,
        )
    except AIServiceError:
        raise  # Let the router handle it
    except Exception as exc:
        raise AIServiceError(
            code="MODEL_INFERENCE_FAILED",
            message=f"AI inference failed: {exc}",
        ) from exc

    # 6. Assemble API response
    response = _assemble_response(
        task,
        result,
        geo_meta=primary_geo_meta,
        secondary_geo_meta=secondary_geo_meta,
    )

    # 7. Log to DB (non-blocking, best-effort)
    await _log_query_to_db(request, task, response, image_checksums)

    return response
