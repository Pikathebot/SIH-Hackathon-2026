"""
Upload router — POST /api/v1/upload and GET /api/v1/assets/{asset_id}

Handles:
1. Streaming multipart upload of large satellite files (>150MB to multi-GB GeoTIFF/JP2).
2. Disk caching with unique asset IDs.
3. Fast normalized PNG preview generation.
4. Geospatial metadata extraction.
5. TTL-based file cleanup.
"""

import base64
import io
import logging
import os
from pathlib import Path
import shutil
import time
import uuid
from typing import Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from PIL import Image

from app.geotiff import is_geotiff, process_geotiff, get_geotiff_info
from app.models.api import ErrorDetail, ErrorResponse, GeospatialMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["upload"])

UPLOAD_DIR = Path("backend/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# TTL for uploaded assets (2 hours in seconds)
UPLOAD_TTL_SECONDS = 2 * 60 * 60


def cleanup_expired_uploads(ttl_seconds: int = UPLOAD_TTL_SECONDS) -> int:
    """Removes upload files older than ttl_seconds from the disk cache."""
    now = time.time()
    deleted_count = 0
    try:
        for item in UPLOAD_DIR.iterdir():
            if item.is_file():
                file_age = now - item.stat().st_mtime
                if file_age > ttl_seconds:
                    try:
                        item.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.warning("Failed to delete expired asset %s: %s", item.name, e)
    except Exception as exc:
        logger.warning("Error during upload cleanup: %s", exc)
    return deleted_count


class UploadResponse(BaseModel):
    asset_id: str
    filename: str
    url: str
    preview_base64: str
    format: str  # "geotiff" | "standard"
    width: int
    height: int
    size_bytes: int
    geospatial: Optional[GeospatialMetadata] = None


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_file(file: UploadFile = File(...)):
    """
    POST /api/v1/upload — Stream large satellite images/GeoTIFFs directly to disk cache.
    Returns asset ID, fast browser preview, and geospatial metadata.
    """
    # Proactively clean expired files
    cleanup_expired_uploads()

    asset_id = f"ast_{uuid.uuid4().hex[:16]}"
    original_name = file.filename or "uploaded_image.tif"
    clean_ext = Path(original_name).suffix.lower() or ".tif"
    target_path = UPLOAD_DIR / f"{asset_id}{clean_ext}"

    try:
        # Stream file directly in 1MB chunks to disk
        total_bytes = 0
        with open(target_path, "wb") as f_out:
            while chunk := await file.read(1024 * 1024):
                f_out.write(chunk)
                total_bytes += len(chunk)

        logger.info("Uploaded asset %s (%s, %d bytes) saved to %s", asset_id, original_name, total_bytes, target_path)

        # Process GeoTIFF / Image for preview and geospatial metadata
        pil_img, geo_meta = process_geotiff(target_path, max_dim=1024)

        # Generate lightweight PNG preview
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        preview_data_url = f"data:image/png;base64,{png_b64}"

        geospatial = None
        is_geo = geo_meta is not None
        if geo_meta and geo_meta.image_bounds:
            geospatial = GeospatialMetadata(
                crs=geo_meta.crs,
                image_bounds=geo_meta.image_bounds,
                geo_boxes=None,
            )

        orig_w = geo_meta.raw_size[0] if geo_meta else pil_img.width
        orig_h = geo_meta.raw_size[1] if geo_meta else pil_img.height

        return UploadResponse(
            asset_id=asset_id,
            filename=original_name,
            url=f"/api/v1/assets/{asset_id}",
            preview_base64=preview_data_url,
            format="geotiff" if is_geo else "standard",
            width=orig_w,
            height=orig_h,
            size_bytes=total_bytes,
            geospatial=geospatial,
        )

    except Exception as exc:
        logger.exception("Failed to process uploaded file: %s", exc)
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message=f"Failed to process uploaded file: {exc}",
                )
            ).model_dump(),
        )


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    """
    GET /api/v1/assets/{asset_id} — Retrieve stored image file by asset ID.
    """
    # Find matching file with any extension in upload directory
    matches = list(UPLOAD_DIR.glob(f"{asset_id}.*"))
    if not matches or not matches[0].exists():
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found or expired.")

    asset_path = matches[0]
    return FileResponse(path=str(asset_path))
