"""
Preview endpoint — POST /api/v1/preview

Accepts an image payload (raw base64 or URL) and returns a browser-renderable
PNG data URL (with robust 2%-98% radiometric normalization for GeoTIFFs)
and extracted geospatial coordinate bounds.
"""

import base64
import io
import logging
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from PIL import Image

from app.geotiff import is_geotiff, process_geotiff
from app.models.api import ErrorDetail, ErrorResponse, GeospatialMetadata
from app.orchestrator import _decode_image, QueryValidationError

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
        500: {"model": ErrorResponse},
    },
)
async def generate_preview(request: PreviewRequest):
    """
    POST /api/v1/preview — generate a web-friendly PNG preview for any image/GeoTIFF.
    """
    try:
        data = request.url_or_base64.strip()
        pil_img, geo_meta = _decode_image(data)

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
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error=ErrorDetail(code=exc.code, message=exc.message, detail=exc.detail)
            ).model_dump(),
        )
    except Exception as exc:
        logger.exception("Failed to generate preview")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="Failed to generate image preview.",
                    detail=str(exc),
                )
            ).model_dump(),
        )
