"""
Preview endpoint — POST /api/v1/preview

Accepts an image payload (raw base64 or URL) and returns a browser-renderable
PNG data URL (with robust 2%-98% radiometric normalization for GeoTIFFs)
and extracted geospatial coordinate bounds.
"""

import asyncio
import base64
import io
import logging
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter
from PIL import Image

from app.geotiff import is_geotiff, process_geotiff
from app.errors import error_response
from app.models.api import ErrorResponse, GeospatialMetadata
from app.orchestrator import _decode_image, QueryValidationError
from app.ratelimit import QueryRateLimitDep
from app.security import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["preview"])


class PreviewRequest(BaseModel):
    url_or_base64: str = Field(..., description="Base64 encoded image or HTTP/HTTPS URL")


class PreviewResponse(BaseModel):
    preview_base64: str
    format: str  # "geotiff" | "standard"
    geospatial: Optional[GeospatialMetadata] = None
    width: int
    height: int


@router.post(
    "/preview",
    response_model=PreviewResponse,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def generate_preview(request: PreviewRequest, user: CurrentUser, _limit: QueryRateLimitDep = None):
    """
    POST /api/v1/preview — generate a web-friendly PNG preview for any image/GeoTIFF.
    """
    try:
        data = request.url_or_base64.strip()
        pil_img, geo_meta = await asyncio.to_thread(_decode_image, data)

        # Convert PIL Image to PNG base64 data URI
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

        return PreviewResponse(
            preview_base64=preview_data_url,
            format="geotiff" if is_geo else "standard",
            geospatial=geospatial,
            width=pil_img.width,
            height=pil_img.height,
        )

    except QueryValidationError as exc:
        return error_response(400, exc.code, exc.message, exc.detail)
    except Exception:
        logger.exception("Failed to generate preview")  # traceback logged under the request id
        return error_response(500, "INTERNAL_ERROR", "Failed to generate image preview.")
