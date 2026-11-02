"""
Upload router: POST /api/v1/upload and GET /api/v1/assets/{asset_id} (API_CONTRACT.md §5).

- Authenticated; files are stored per user at DATA_DIR/uploads/<user_id>/<asset_id>.<ext>
  and recorded in `images` with the owner, original filename and size.
- Streams to disk in 1 MB chunks (multi-GB GeoTIFF/JP2), enforcing MAX_UPLOAD_MB as it goes.
- The type is decided by magic bytes, not by the client's filename or content type.
- Returns a normalised PNG preview and geospatial metadata.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
from typing import Optional

from fastapi import APIRouter, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import DATA_DIR, UPLOADS_DIR, settings
from app.errors import ApiError
from app.geotiff import process_geotiff
from app.image_sources import EXTENSIONS, resolve_owned_asset, sniff_image_type
from app.models.api import ErrorResponse, GeospatialMetadata
from app.models.db import ImageRecord, new_id
from app.security import CurrentUser, DbSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["upload"])

_CHUNK = 1024 * 1024


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


def _build_preview(path) -> tuple[str, object, object]:
    pil_img, geo_meta = process_geotiff(path, max_dim=1024)
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), pil_img, geo_meta


class StorageResponse(BaseModel):
    used_bytes: int
    quota_bytes: Optional[int]  # None = unlimited (USER_QUOTA_MB=0)
    asset_count: int


async def _usage(db, user_id: str) -> tuple[int, int]:
    used, count = (await db.execute(
        select(func.coalesce(func.sum(ImageRecord.size_bytes), 0), func.count(ImageRecord.id))
        .where(ImageRecord.user_id == user_id)
    )).one()
    return int(used), int(count)


@router.post("/upload", response_model=UploadResponse,
             responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse},
                        413: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
async def upload_file(user: CurrentUser, db: DbSession, file: UploadFile = File(...)) -> UploadResponse:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    # Per-user storage quota (API v2.3.0): what is left after this user's existing uploads
    quota_left = None
    if settings.user_quota_mb > 0:
        used, _ = await _usage(db, user.id)
        quota_left = settings.user_quota_mb * 1024 * 1024 - used
        if quota_left <= 0:
            raise ApiError(413, "QUOTA_EXCEEDED",
                           f"Your storage quota of {settings.user_quota_mb} MB is full.")
    original_name = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:255] or "upload"

    first = await file.read(_CHUNK)
    kind = sniff_image_type(first[:16])
    if kind is None:
        raise ApiError(400, "UNSUPPORTED_FORMAT",
                       "Unsupported file type. Upload a GeoTIFF, JPEG 2000, PNG or JPEG image.")

    asset_id = new_id()
    user_dir = UPLOADS_DIR / user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    target = user_dir / f"{asset_id}{EXTENSIONS[kind]}"
    sha = hashlib.sha256()
    total = 0
    try:
        with open(target, "wb") as out:
            chunk = first
            while chunk:
                total += len(chunk)
                if total > max_bytes:
                    raise ApiError(413, "PAYLOAD_TOO_LARGE", f"File is larger than {settings.max_upload_mb} MB.")
                if quota_left is not None and total > quota_left:
                    raise ApiError(413, "QUOTA_EXCEEDED",
                                   f"This upload would exceed your storage quota of {settings.user_quota_mb} MB.")
                sha.update(chunk)
                out.write(chunk)
                chunk = await file.read(_CHUNK)

        try:
            preview, pil_img, geo_meta = await asyncio.to_thread(_build_preview, target)
        except Exception as exc:
            logger.warning("Could not decode upload %s (%s): %s", asset_id, kind, exc)
            raise ApiError(400, "UNSUPPORTED_FORMAT", "The file could not be read as an image.") from exc

        db.add(ImageRecord(
            id=asset_id,
            modality="optical",  # provisional; each query states the image's modality explicitly
            storage_path=target.relative_to(DATA_DIR).as_posix(),
            checksum=sha.hexdigest(), user_id=user.id, filename=original_name, size_bytes=total,
        ))
        await db.commit()
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    logger.info("User %s uploaded asset %s (%s, %d bytes)", user.id, asset_id, kind, total)
    geospatial = None
    if geo_meta and geo_meta.image_bounds:
        geospatial = GeospatialMetadata(crs=geo_meta.crs, image_bounds=geo_meta.image_bounds, geo_boxes=None)
    return UploadResponse(
        asset_id=asset_id, filename=original_name, url=f"/api/v1/assets/{asset_id}",
        preview_base64=preview, format="geotiff" if geo_meta is not None else "standard",
        width=geo_meta.raw_size[0] if geo_meta else pil_img.width,
        height=geo_meta.raw_size[1] if geo_meta else pil_img.height,
        size_bytes=total, geospatial=geospatial,
    )


@router.get("/assets/{asset_id}", responses={404: {"model": ErrorResponse}})
async def get_asset(asset_id: str, user: CurrentUser, db: DbSession) -> FileResponse:
    """The original uploaded file, for its owner only."""
    row, path = await resolve_owned_asset(db, user.id, asset_id)
    return FileResponse(path=str(path), filename=row.filename or path.name)


def _ensure_preview_png(src, dst) -> None:
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    pil_img, _ = process_geotiff(src, max_dim=1024)
    tmp = dst.with_suffix(".tmp")
    pil_img.convert("RGB").save(tmp, format="PNG")
    tmp.replace(dst)  # atomic, so concurrent requests never serve a half-written file


@router.get("/assets/{asset_id}/preview", responses={404: {"model": ErrorResponse}})
async def get_asset_preview(asset_id: str, user: CurrentUser, db: DbSession) -> FileResponse:
    """Browser-renderable PNG preview (≤1024 px) of an owned asset (API_CONTRACT v2.1.0). Cached on disk."""
    _, path = await resolve_owned_asset(db, user.id, asset_id)
    preview = path.with_name(f"{path.stem}.preview.png")
    try:
        await asyncio.to_thread(_ensure_preview_png, path, preview)
    except Exception as exc:
        logger.warning("Could not render preview for asset %s: %s", asset_id, exc)
        raise ApiError(404, "NOT_FOUND", "No preview available for this image.") from exc
    return FileResponse(path=str(preview), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/assets/{asset_id}", status_code=204, responses={404: {"model": ErrorResponse}})
async def delete_asset(asset_id: str, user: CurrentUser, db: DbSession) -> Response:
    """Delete an owned asset: file, cached preview and row (API_CONTRACT v2.3.0). History keeps the id."""
    row, path = await resolve_owned_asset(db, user.id, asset_id)
    await db.delete(row)
    await db.commit()
    for f in (path, path.with_name(f"{path.stem}.preview.png")):
        try:
            f.unlink(missing_ok=True)
        except OSError as exc:  # e.g. file open on Windows; the row is gone, so it is unreachable anyway
            logger.warning("Could not remove %s for deleted asset %s: %s", f.name, asset_id, exc)
    logger.info("User %s deleted asset %s", user.id, asset_id)
    return Response(status_code=204)


@router.get("/storage", response_model=StorageResponse)
async def storage_usage(user: CurrentUser, db: DbSession) -> StorageResponse:
    used, count = await _usage(db, user.id)
    quota = settings.user_quota_mb * 1024 * 1024 if settings.user_quota_mb > 0 else None
    return StorageResponse(used_bytes=used, quota_bytes=quota, asset_count=count)
