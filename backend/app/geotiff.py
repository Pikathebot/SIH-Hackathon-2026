"""
GeoTIFF processing utility for SatQuery AI.

Handles:
1. Fast GeoTIFF format detection (magic byte signature).
2. Multi-band extraction (Sentinel-2 B4/B3/B2, SAR VV/VH).
3. Radiometric normalization (robust 2%-98% percentile linear stretch).
4. Spatial reference & CRS re-projection to WGS84 (EPSG:4326).
5. Forward projection: Pixel bounding boxes -> WGS84 GeoJSON polygons.
"""

from dataclasses import dataclass
import io
import logging
from typing import List, Optional, Tuple, Union
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# GeoTIFF magic byte signatures
_TIFF_MAGIC = (
    b"II*\x00",  # Little-endian TIFF
    b"MM\x00*",  # Big-endian TIFF
    b"II+\x00",  # Little-endian BigTIFF
    b"MM\x00+",  # Big-endian BigTIFF
)


@dataclass
class GeoMetadata:
    crs: str
    image_bounds: List[float]  # [min_lon, min_lat, max_lon, max_lat] in WGS84
    affine_transform: Tuple[float, float, float, float, float, float]
    raw_size: Tuple[int, int]  # (width, height)
    scaled_size: Tuple[int, int]  # (width, height)
    scale_factor: Tuple[float, float]  # (scale_x, scale_y)


def is_geotiff(data_bytes: bytes) -> bool:
    """Checks if raw bytes start with a valid TIFF/GeoTIFF header."""
    if len(data_bytes) < 4:
        return False
    header = data_bytes[:4]
    return any(header.startswith(m) for m in _TIFF_MAGIC)


def normalize_band_percentile(
    band_array: np.ndarray,
    p_low: float = 2.0,
    p_high: float = 98.0,
) -> np.ndarray:
    """
    Applies robust 2%-98% percentile linear stretch to high-dynamic-range
    reflectance or radar amplitude arrays into [0, 255] uint8.
    """
    valid_mask = np.isfinite(band_array)
    if not np.any(valid_mask):
        return np.zeros_like(band_array, dtype=np.uint8)

    valid_vals = band_array[valid_mask]
    v_min = float(np.percentile(valid_vals, p_low))
    v_max = float(np.percentile(valid_vals, p_high))

    if v_max <= v_min:
        v_min = float(np.min(valid_vals))
        v_max = float(np.max(valid_vals))

    if v_max <= v_min:
        return np.zeros_like(band_array, dtype=np.uint8)

    stretched = (band_array - v_min) / (v_max - v_min + 1e-6)
    stretched = np.clip(stretched, 0.0, 1.0) * 255.0
    return stretched.astype(np.uint8)


def process_geotiff(
    data_bytes: bytes,
    max_dim: int = 2048,
) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    """
    Decodes raw GeoTIFF bytes into a normalized 8-bit RGB PIL.Image and
    extracts geospatial metadata (CRS, WGS84 bounding box, Affine transform).

    Returns:
        (pil_image, geo_metadata)
    """
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.warp import transform_bounds
    import pyproj

    try:
        with MemoryFile(data_bytes) as memfile:
            with memfile.open() as src:
                n_bands = src.count
                width = src.width
                height = src.height
                crs_obj = src.crs
                transform = src.transform

                # 1. Read bands
                if n_bands >= 3:
                    if n_bands >= 4:
                        try:
                            r = src.read(4)
                            g = src.read(3)
                            b = src.read(2)
                        except IndexError:
                            r = src.read(1)
                            g = src.read(2)
                            b = src.read(3)
                    else:
                        r = src.read(1)
                        g = src.read(2)
                        b = src.read(3)

                    r_u8 = normalize_band_percentile(r)
                    g_u8 = normalize_band_percentile(g)
                    b_u8 = normalize_band_percentile(b)
                    rgb_array = np.stack([r_u8, g_u8, b_u8], axis=-1)
                    pil_img = Image.fromarray(rgb_array, mode="RGB")

                elif n_bands == 2:
                    b1 = src.read(1)
                    b2 = src.read(2)
                    b1_u8 = normalize_band_percentile(b1)
                    b2_u8 = normalize_band_percentile(b2)
                    eps = 1e-6
                    ratio = (b1.astype(np.float32) + eps) / (b2.astype(np.float32) + eps)
                    ratio_u8 = normalize_band_percentile(ratio)
                    rgb_array = np.stack([b1_u8, b2_u8, ratio_u8], axis=-1)
                    pil_img = Image.fromarray(rgb_array, mode="RGB")

                else:
                    b1 = src.read(1)
                    b1_u8 = normalize_band_percentile(b1)
                    rgb_array = np.stack([b1_u8, b1_u8, b1_u8], axis=-1)
                    pil_img = Image.fromarray(rgb_array, mode="RGB")

                # 2. Extract Geospatial Coordinates
                geo_meta = None
                if crs_obj:
                    src_crs_str = crs_obj.to_string()
                    try:
                        wgs84_bounds = transform_bounds(
                            crs_obj,
                            pyproj.CRS.from_epsg(4326),
                            src.bounds.left,
                            src.bounds.bottom,
                            src.bounds.right,
                            src.bounds.top,
                        )
                        bounds_list = [
                            float(round(wgs84_bounds[0], 6)),  # min_lon
                            float(round(wgs84_bounds[1], 6)),  # min_lat
                            float(round(wgs84_bounds[2], 6)),  # max_lon
                            float(round(wgs84_bounds[3], 6)),  # max_lat
                        ]
                    except Exception as e:
                        logger.warning("Failed to project bounds to WGS84: %s", e)
                        bounds_list = [
                            float(round(src.bounds.left, 6)),
                            float(round(src.bounds.bottom, 6)),
                            float(round(src.bounds.right, 6)),
                            float(round(src.bounds.top, 6)),
                        ]

                    # 3. Handle Scaling if oversized
                    orig_size = (width, height)
                    scaled_size = orig_size
                    scale_x = 1.0
                    scale_y = 1.0

                    if max(width, height) > max_dim:
                        if width >= height:
                            new_w = max_dim
                            new_h = int(height * (max_dim / width))
                        else:
                            new_h = max_dim
                            new_w = int(width * (max_dim / height))
                        pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BICUBIC)
                        scaled_size = (new_w, new_h)
                        scale_x = width / float(new_w)
                        scale_y = height / float(new_h)

                    geo_meta = GeoMetadata(
                        crs=src_crs_str,
                        image_bounds=bounds_list,
                        affine_transform=(
                            transform.a,
                            transform.b,
                            transform.c,
                            transform.d,
                            transform.e,
                            transform.f,
                        ),
                        raw_size=orig_size,
                        scaled_size=scaled_size,
                        scale_factor=(scale_x, scale_y),
                    )

                return pil_img, geo_meta

    except Exception as e:
        logger.warning("Rasterio GeoTIFF extraction failed: %s. Falling back to PIL.", e)
        buf = io.BytesIO(data_bytes)
        img = Image.open(buf).convert("RGB")
        return img, None


def pixel_boxes_to_geo_polygons(
    pixel_boxes: List[List[int]],
    geo_meta: GeoMetadata,
) -> List[List[List[float]]]:
    """
    Projects 2D pixel bounding boxes [[x1, y1, x2, y2], ...] into
    WGS84 GeoJSON coordinate polygons:
    [
      [[lon1, lat1], [lon2, lat1], [lon2, lat2], [lon1, lat2], [lon1, lat1]],
      ...
    ]
    """
    import pyproj
    import rasterio.transform

    if not geo_meta or not geo_meta.affine_transform:
        return []

    sx, sy = geo_meta.scale_factor
    a, b, c, d, e, f = geo_meta.affine_transform
    src_transform = rasterio.Affine(a, b, c, d, e, f)

    try:
        src_crs = pyproj.CRS.from_user_input(geo_meta.crs)
        wgs84_crs = pyproj.CRS.from_epsg(4326)
        transformer = pyproj.Transformer.from_crs(src_crs, wgs84_crs, always_xy=True)
    except Exception as exc:
        logger.warning("CRS transformation setup failed (%s), using direct projection", exc)
        transformer = None

    polygons = []

    for box in pixel_boxes:
        if len(box) < 4:
            continue
        px1, py1, px2, py2 = box[:4]

        rx1, ry1 = px1 * sx, py1 * sy
        rx2, ry2 = px2 * sx, py2 * sy

        x_tl, y_tl = rasterio.transform.xy(src_transform, ry1, rx1, offset="center")
        x_tr, y_tr = rasterio.transform.xy(src_transform, ry1, rx2, offset="center")
        x_br, y_br = rasterio.transform.xy(src_transform, ry2, rx2, offset="center")
        x_bl, y_bl = rasterio.transform.xy(src_transform, ry2, rx1, offset="center")

        if transformer is not None:
            lon_tl, lat_tl = transformer.transform(x_tl, y_tl)
            lon_tr, lat_tr = transformer.transform(x_tr, y_tr)
            lon_br, lat_br = transformer.transform(x_br, y_br)
            lon_bl, lat_bl = transformer.transform(x_bl, y_bl)
        else:
            lon_tl, lat_tl = x_tl, y_tl
            lon_tr, lat_tr = x_tr, y_tr
            lon_br, lat_br = x_br, y_br
            lon_bl, lat_bl = x_bl, y_bl

        poly = [
            [float(round(lon_tl, 6)), float(round(lat_tl, 6))],
            [float(round(lon_tr, 6)), float(round(lat_tr, 6))],
            [float(round(lon_br, 6)), float(round(lat_br, 6))],
            [float(round(lon_bl, 6)), float(round(lat_bl, 6))],
            [float(round(lon_tl, 6)), float(round(lat_tl, 6))],
        ]
        polygons.append(poly)

    return polygons
