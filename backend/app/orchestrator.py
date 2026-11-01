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
import re
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from app.config import AI_SERVICE_MODE
from app.geotiff import (
    GeoMetadata,
    is_geotiff,
    pixel_boxes_to_geo_polygons,
    process_geotiff,
)
from app.tiling import run_tiled_detection
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

# Resolve the configured engine (AI_ENGINE x AI_SERVICE_MODE) — see app/engines.py
from app.config import AI_ENGINE, LLM_INTENT_ENABLED
from app.engines import Engine, build_engine

ENGINE: Optional[Engine] = None
try:
    ENGINE = build_engine(AI_ENGINE, AI_SERVICE_MODE)
    _run_vqa = ENGINE.run_vqa
    _run_captioning = ENGINE.run_captioning
    _run_detection = ENGINE.run_detection
    _run_change_detection = ENGINE.run_change_detection
    _run_fusion = ENGINE.run_fusion
    _rsunivlm_loaded = True
    _fusion_loaded = True
    logger.info("AI engine loaded: engine=%s mode=%s", ENGINE.name, ENGINE.mode)
except (ImportError, AttributeError) as exc:
    logger.warning("AI engine import failed (%s), using fallback stubs", exc)

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
def classify_intent(request: QueryRequest) -> str:
    """
    Classify query intent → one of the canonical task values.

    Values from CONTRACT.md §5: vqa | captioning | detection | change_detection | fusion
    """
    images = request.images
    query_raw = request.query.strip()
    query_lower = query_raw.lower()
    modalities = sorted(img.modality for img in images)

    # Two-image tasks are determined purely by modality combination
    if len(images) == 2:
        if modalities == ["optical", "optical"]:
            return "change_detection"
        if modalities == ["optical", "sar"]:
            return "fusion"

    # Single-image: disambiguate by query structure and action intent

    # 1. Explicit pixel segmentation / masking / bounding box actions always trigger detection
    if re.search(r"\b(?:segment|segmentation|highlight|mask|bounding\s+box(?:es)?|draw\s+box(?:es)?)\b", query_lower):
        return "detection"

    # 2. Natural descriptive/factual questions (What/Which/Why/How/Is/Are/Name/Can you...)
    # Route to VQA unless the question explicitly asks "Where is/are..." (spatial localization)
    is_question = bool(re.search(r"^(?:what|which|why|how|is\s+there|are\s+there|can\s+you|does|name\s+the|tell\s+me)\b", query_lower))
    if is_question:
        if re.search(r"\bwhere\s+(?:is|are)\b", query_lower):
            return "detection"
        return "vqa"

    # 3. Detection & visual localization commands ("Locate the airport", "Find the river", "Where are the aircraft")
    if re.search(r"\b(?:locate|find|detect|where)\b", query_lower):
        return "detection"

    # 4. Captioning commands ("Describe this scene", "Summarize the image", "Caption this")
    if re.search(r"\b(?:caption|describe|description|summarize|summarise|overview|what\s+do\s+you\s+see|what\s+is\s+in\s+this\s+image)\b", query_lower):
        return "captioning"

    # Default: VQA
    return "vqa"


_SINGLE_IMAGE_TASKS = ("vqa", "captioning", "detection")


async def _maybe_llm_intent(request: QueryRequest, keyword_task: str) -> str:
    """Refine single-image intent with the engine's LLM classifier if enabled."""
    if (
        ENGINE is None
        or ENGINE.classify_intent is None
        or ENGINE.mode != "real"
        or not LLM_INTENT_ENABLED
        or len(request.images) != 1
    ):
        return keyword_task
    modalities = [img.modality for img in request.images]
    try:
        llm_task = await asyncio.wait_for(
            asyncio.to_thread(ENGINE.classify_intent, request.query, modalities), timeout=20
        )
    except Exception as exc:  # timeout / server down → keep keyword result
        logger.warning("LLM intent classification failed (%s); using keyword task=%s", exc, keyword_task)
        return keyword_task
    if llm_task in _SINGLE_IMAGE_TASKS:
        if llm_task != keyword_task:
            logger.info("LLM intent override: keyword=%s → llm=%s", keyword_task, llm_task)
        return llm_task
    return keyword_task


# ---------------------------------------------------------------------------
# Image decoding — base64/URL/Asset → PIL.Image at the API boundary
# AI modules work with PIL.Image.Image objects, never raw base64.
# ---------------------------------------------------------------------------
def _decode_file(path: Path) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    """Decode a server-side file (an owned, already-resolved asset). Never called with client paths."""
    img, geo_meta = process_geotiff(path)
    img._file_source = str(path)  # lets large rasters use the tiled detection path
    img._geo_meta = geo_meta
    return img, geo_meta


def _decode_image(url_or_base64: str) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    """Decode a base64 payload (optionally a data: URI) or a public http(s) URL to a PIL Image.

    Uploaded assets are resolved (with an ownership check) by process_query before this
    is called; local filesystem paths are never accepted (API_CONTRACT v2.0.0).
    """
    from app.config import settings
    from app.image_sources import UnsafeUrlError, fetch_public_url, parse_asset_ref

    data = url_or_base64.strip()
    if parse_asset_ref(data):
        raise QueryValidationError(
            code="UNSUPPORTED_FORMAT",
            message="Uploaded images must be referenced through a query's asset_id.",
        )

    # 1. Remote URL
    if data.startswith(("http://", "https://")):
        try:
            image_bytes = fetch_public_url(data, max_bytes=settings.max_upload_mb * 1024 * 1024)
        except UnsafeUrlError as exc:
            raise QueryValidationError(code="UNSUPPORTED_FORMAT", message=str(exc)) from exc
        except Exception as exc:
            raise QueryValidationError(
                code="UNSUPPORTED_FORMAT",
                message="Failed to download the image from the URL.",
                detail=str(exc),
            ) from exc
        return _decode_bytes(image_bytes)

    # 2. data URI / raw base64
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        image_bytes = base64.b64decode(data, validate=False)
        return _decode_bytes(image_bytes)
    except QueryValidationError:
        raise
    except Exception:
        pass

    raise QueryValidationError(
        code="UNSUPPORTED_FORMAT",
        message="Could not decode image. Provide a valid base64 string, an uploaded asset, or an https URL.",
    )


def _decode_bytes(image_bytes: bytes) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    if is_geotiff(image_bytes):
        img, geo_meta = process_geotiff(image_bytes)
        img._geo_meta = geo_meta
        return img, geo_meta
    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGB"), None
    except Exception as exc:
        raise QueryValidationError(code="UNSUPPORTED_FORMAT", message="Unsupported or corrupt image data.") from exc


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
        primary_img = decoded_images[0]
        # Check if query is bounding box (VG) or segmentation (SEG)
        from ai_service.rsunivlm.parsing import resolve_detection_mode
        resolved_mode = resolve_detection_mode(request.query)

        file_src = getattr(primary_img, "_file_source", None)
        geo_meta = getattr(primary_img, "_geo_meta", None)

        if resolved_mode == "bbox" and file_src and geo_meta and max(geo_meta.raw_size) > 1024:
            logger.info("Routing localized bbox detection through high-resolution tiled engine for %s", file_src)
            return run_tiled_detection(
                raster_source=file_src,
                query=request.query,
                detection_fn=_run_detection,
                chip_size=1024,
                overlap_ratio=0.15,
            )
        return _run_detection(primary_img, request.query)

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
    params = dict(meta.get("parameters") or {})
    if geo_meta and geo_meta.band_resolution_tier:
        params["band_resolution_tier"] = geo_meta.band_resolution_tier
    if geo_meta and geo_meta.band_resolution_warning:
        params["band_resolution_warning"] = geo_meta.band_resolution_warning

    execution_summary = ExecutionSummary(
        selected_task=task,
        tool_used=meta["tool_used"],
        parameters=params,
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
# Persistence: images, evidence file and the query row (DATABASE_CONTRACT v1.1.0)
# ---------------------------------------------------------------------------
async def _persist_query(
    db,
    user_id: str,
    request: QueryRequest,
    response: QueryResponse,
    decoded_images: list,
    asset_ids: list[Optional[str]],
    image_checksums: list[str],
) -> str:
    """Store the query so the session history can re-render it. Returns the query id.

    Images sent inline (base64/URL) are saved as the user's assets (PNG) so history
    thumbnails work; uploaded assets are referenced, not copied. visual_evidence is
    written to a JSON file and referenced by path, never stored as base64 in the DB.
    """
    from app.config import DATA_DIR, EVIDENCE_DIR, UPLOADS_DIR
    from app.models.db import AnalysisSession, ImageRecord, QueryRecord, new_id, utc_now

    now = utc_now()
    image_ids: list[str] = []
    for img_input, img, asset_id, checksum in zip(request.images, decoded_images, asset_ids, image_checksums):
        if asset_id:
            image_ids.append(asset_id)
            continue
        image_id = new_id()
        user_dir = UPLOADS_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        path = user_dir / f"{image_id}.png"
        await asyncio.to_thread(img.convert("RGB").save, path, "PNG")
        db.add(ImageRecord(
            id=image_id, modality=img_input.modality, capture_date=img_input.date,
            storage_path=path.relative_to(DATA_DIR).as_posix(), checksum=checksum, created_at=now,
            user_id=user_id, filename=f"{img_input.id}.png", size_bytes=path.stat().st_size,
        ))
        image_ids.append(image_id)

    query_id = new_id()
    ev_dir = EVIDENCE_DIR / user_id
    ev_dir.mkdir(parents=True, exist_ok=True)
    ev_path = ev_dir / f"{query_id}.json"
    await asyncio.to_thread(ev_path.write_text, response.visual_evidence.model_dump_json(), "utf-8")

    es = response.execution_summary
    db.add(QueryRecord(
        id=query_id, query_text=request.query, image_ids=json.dumps(image_ids),
        selected_task=es.selected_task, tool_used=es.tool_used, parameters=json.dumps(es.parameters),
        answer=response.answer, confidence=response.confidence,
        visual_evidence_type=response.visual_evidence.type,
        visual_evidence_ref=ev_path.relative_to(DATA_DIR).as_posix(),
        latency_ms=es.latency_ms, inputs_validated=1, status="success", error_code=None,
        created_at=now, user_id=user_id, session_id=request.session_id,
    ))
    if request.session_id:
        session = await db.get(AnalysisSession, request.session_id)
        if session is not None:
            session.updated_at = now
    await db.commit()
    return query_id


# ---------------------------------------------------------------------------
# Main entry point — called by the router
# ---------------------------------------------------------------------------
async def process_query(request: QueryRequest, user=None, db=None) -> QueryResponse:
    """
    Full orchestrator pipeline:
    validate → check session → resolve assets → classify → decode → dispatch AI →
    assemble response → persist (when called with a user and DB session).
    """
    from app.errors import ApiError
    from app.image_sources import parse_asset_ref, resolve_owned_asset
    from app.models.db import AnalysisSession

    # 1. Validate inputs
    validate_inputs(request)

    # 2. Ownership checks happen before any model work
    if request.session_id:
        session = await db.get(AnalysisSession, request.session_id) if db is not None else None
        if session is None or user is None or session.user_id != user.id:
            raise ApiError(404, "NOT_FOUND", "Analysis session not found.")

    asset_ids: list[Optional[str]] = []
    asset_paths: list[Optional[Path]] = []
    for img in request.images:
        asset_id = img.asset_id or parse_asset_ref(img.url_or_base64)
        if asset_id:
            if user is None or db is None:
                raise ApiError(404, "NOT_FOUND", "Image not found.")
            _, path = await resolve_owned_asset(db, user.id, asset_id)
            asset_ids.append(asset_id)
            asset_paths.append(path)
        else:
            asset_ids.append(None)
            asset_paths.append(None)

    # 3. Classify intent — keyword rules first, then (optionally) the VLM for
    #    single-image queries; any LLM failure keeps the keyword result.
    task = classify_intent(request)
    task = await _maybe_llm_intent(request, task)

    # 4. Decode images (file decode and URL download run off the event loop)
    decoded_pairs = []
    for img, path in zip(request.images, asset_paths):
        if path is not None:
            decoded_pairs.append(await asyncio.to_thread(_decode_file, path))
        else:
            decoded_pairs.append(await asyncio.to_thread(_decode_image, img.url_or_base64))
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

    # 7. Persist for history. Best-effort: a storage failure must not lose the answer.
    if user is not None and db is not None:
        try:
            # Only inline images need hashing; uploaded assets already have a checksum row.
            checksums = [await asyncio.to_thread(_compute_image_checksum, img) if aid is None else ""
                         for img, aid in zip(decoded_images, asset_ids)]
            await _persist_query(db, user.id, request, response, decoded_images, asset_ids, checksums)
        except Exception:
            await db.rollback()
            logger.exception("Failed to persist query (answer still returned)")

    return response
