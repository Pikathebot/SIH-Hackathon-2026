"""
GeoTIFF processing utility for SatQuery AI.

Handles:
1. Fast GeoTIFF format detection (magic byte signature).
2. Multi-band extraction (Sentinel-2 B4/B3/B2, SAR VV/VH).
3. Radiometric normalization (robust 2%-98% percentile linear stretch).
4. Spatial reference & CRS re-projection to WGS84 (EPSG:4326).
5. Forward projection: Pixel bounding boxes -> WGS84 GeoJSON polygons.
6. Windowed block reading for high-resolution sliding-window inference.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import io
import logging
from pathlib import Path
import re
from typing import Generator, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Geospatial raster magic byte signatures (TIFF, BigTIFF, and JPEG 2000 JP2/J2K)
_GEORASTER_MAGIC = (
    b"II*\x00",                              # Little-endian TIFF
    b"MM\x00*",                              # Big-endian TIFF
    b"II+\x00",                              # Little-endian BigTIFF
    b"MM\x00+",                              # Big-endian BigTIFF
    b"\x00\x00\x00\x0cjP  \r\n\x87\n",       # Standard JPEG 2000 (.jp2) file signature
    b"\x00\x00\x00\x0c",                     # Short JP2 box header
    b"\xff\x4f\xff\x51",                     # JPEG 2000 codestream (SOC/SIZ marker .j2k/.j2c)
)
_TIFF_MAGIC = _GEORASTER_MAGIC  # Backward compatibility alias


@dataclass
class GeoMetadata:
    crs: str
    image_bounds: List[float]  # [min_lon, min_lat, max_lon, max_lat] in WGS84
    affine_transform: Tuple[float, float, float, float, float, float]
    raw_size: Tuple[int, int]  # (width, height)
    scaled_size: Tuple[int, int]  # (width, height)
    scale_factor: Tuple[float, float]  # (scale_x, scale_y)
    band_resolution_tier: Optional[str] = None
    band_resolution_warning: Optional[str] = None


def is_geotiff(data_or_path: Union[bytes, str, Path]) -> bool:
    """Checks if raw bytes or a file path start with a valid TIFF/GeoTIFF or JPEG 2000 (JP2) header."""
    if isinstance(data_or_path, (str, Path)):
        p = Path(data_or_path)
        if not p.exists() or not p.is_file():
            return False
        try:
            with open(p, "rb") as f:
                header = f.read(16)
            return any(header.startswith(m) for m in _GEORASTER_MAGIC)
        except Exception:
            return False

    data_bytes = data_or_path
    if len(data_bytes) < 4:
        return False
    return any(data_bytes.startswith(m) for m in _GEORASTER_MAGIC)


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
        if v_max > 0:
            return np.clip(band_array, 0, 255).astype(np.uint8)
        return np.zeros_like(band_array, dtype=np.uint8)

    stretched = (band_array - v_min) / (v_max - v_min + 1e-6)
    stretched = np.clip(stretched, 0.0, 1.0) * 255.0
    return stretched.astype(np.uint8)


def _resolve_rgb_bands(src) -> Tuple[Tuple[int, int, int], str, Optional[str]]:
    """
    Dynamically identifies 1-based band indices (r, g, b) and returns:
      ((r_idx, g_idx, b_idx), resolution_tier, optional_warning)

    Tier 1: src.colorinterp (ColorInterp.red, green, blue)
    Tier 2: src.descriptions / src.tags() matching B04/B03/B02, B4/B3/B2, red/green/blue
    Tier 3: Sentinel-2 Full Stack Heuristic (n_bands >= 12 -> 4, 3, 2)
    Tier 4: Default for 3/4-band stacks -> (1, 2, 3) with unverified metadata warning
    """
    n_bands = src.count
    if n_bands < 3:
        return ((1, 1, 1), "default_123", None)

    # ── Tier 1: src.colorinterp ──────────────────────────────────────
    try:
        from rasterio.enums import ColorInterp
        interps = list(src.colorinterp)
        if ColorInterp.red in interps and ColorInterp.green in interps and ColorInterp.blue in interps:
            r_idx = interps.index(ColorInterp.red) + 1
            g_idx = interps.index(ColorInterp.green) + 1
            b_idx = interps.index(ColorInterp.blue) + 1
            logger.debug("GeoTIFF band resolution [Tier 1: colorinterp] -> R:%d, G:%d, B:%d", r_idx, g_idx, b_idx)
            return ((r_idx, g_idx, b_idx), "colorinterp", None)
    except Exception as e:
        logger.debug("ColorInterp inspection skipped: %s", e)

    # ── Tier 2: src.descriptions / src.tags() ────────────────────────
    try:
        r_match = None
        g_match = None
        b_match = None

        r_tokens = ("b04", "b4", "red", "band4", "band04")
        g_tokens = ("b03", "b3", "green", "band3", "band03")
        b_tokens = ("b02", "b2", "blue", "band2", "band02")

        for i in range(1, n_bands + 1):
            d = ""
            if src.descriptions and len(src.descriptions) >= i and src.descriptions[i - 1]:
                d = src.descriptions[i - 1]
            else:
                tags = src.tags(i)
                d = tags.get("NAME") or tags.get("DESCRIPTION") or tags.get("BAND_NAME") or tags.get("color") or ""
            clean_d = re.sub(r"[^a-z0-9]", "", d.lower())
            if not clean_d:
                continue

            if not r_match and any(t in clean_d for t in r_tokens):
                r_match = i
            elif not g_match and any(t in clean_d for t in g_tokens):
                g_match = i
            elif not b_match and any(t in clean_d for t in b_tokens):
                b_match = i

        if r_match and g_match and b_match and len({r_match, g_match, b_match}) == 3:
            logger.debug("GeoTIFF band resolution [Tier 2: band_description_match] -> R:%d, G:%d, B:%d", r_match, g_match, b_match)
            return ((r_match, g_match, b_match), "band_description_match", None)
    except Exception as e:
        logger.debug("Band description matching skipped: %s", e)

    # ── Tier 3: Sentinel-2 Full Stack Heuristic (n_bands >= 12) ─────
    if n_bands >= 12:
        logger.debug("GeoTIFF band resolution [Tier 3: sentinel2_full_stack_heuristic] -> R:4, G:3, B:2")
        return ((4, 3, 2), "sentinel2_full_stack_heuristic", None)

    # ── Tier 4: Default for 3/4-band stacks (standard RGB/RGBN/RGBA) ─
    logger.debug("GeoTIFF band resolution [Tier 4: default_123] -> R:1, G:2, B:3 (unverified fallback)")
    warning_msg = (
        "No photometric or band description metadata found in GeoTIFF. "
        "Rendered with default [1:Red, 2:Green, 3:Blue] channel ordering."
    )
    return ((1, 2, 3), "default_123", warning_msg)


@contextmanager
def open_georaster(source: Union[bytes, str, Path]) -> Generator:
    """
    Context manager yielding an open Rasterio DatasetReader from either
    in-memory bytes or a file path on disk.
    """
    import rasterio
    from rasterio.io import MemoryFile

    if isinstance(source, (str, Path)):
        p = Path(source)
        with rasterio.open(str(p)) as src:
            yield src
    else:
        with MemoryFile(source) as memfile:
            with memfile.open() as src:
                yield src


def get_geotiff_info(source: Union[bytes, str, Path]) -> Optional[GeoMetadata]:
    """
    Extracts geospatial metadata and dimensions without reading the full raster pixels.
    """
    from rasterio.warp import transform_bounds
    import pyproj

    try:
        with open_georaster(source) as src:
            width = src.width
            height = src.height
            crs_obj = src.crs
            transform = src.transform

            (r_idx, g_idx, b_idx), band_tier, band_warn = _resolve_rgb_bands(src)

            bounds_list = [
                float(round(src.bounds.left, 6)),
                float(round(src.bounds.bottom, 6)),
                float(round(src.bounds.right, 6)),
                float(round(src.bounds.top, 6)),
            ]
            src_crs_str = crs_obj.to_string() if crs_obj else "EPSG:4326"

            if crs_obj:
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
                        float(round(wgs84_bounds[0], 6)),
                        float(round(wgs84_bounds[1], 6)),
                        float(round(wgs84_bounds[2], 6)),
                        float(round(wgs84_bounds[3], 6)),
                    ]
                except Exception as e:
                    logger.debug("Reprojection to WGS84 failed: %s", e)

            return GeoMetadata(
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
                raw_size=(width, height),
                scaled_size=(width, height),
                scale_factor=(1.0, 1.0),
                band_resolution_tier=band_tier,
                band_resolution_warning=band_warn,
            )
    except Exception as exc:
        logger.debug("Failed to extract GeoTIFF info: %s", exc)
        return None


def read_geotiff_window(
    source: Union[bytes, str, Path],
    col_off: int,
    row_off: int,
    width: int,
    height: int,
    out_shape: Optional[Tuple[int, int]] = None,
) -> Optional[Image.Image]:
    """
    Reads a specific bounding window from a GeoTIFF raster, resolves bands,
    normalizes to uint8, and returns a PIL RGB Image.
    """
    import rasterio.windows
    from rasterio.enums import Resampling

    try:
        with open_georaster(source) as src:
            window = rasterio.windows.Window(col_off, row_off, width, height)
            n_bands = src.count

            if n_bands >= 3:
                (r_idx, g_idx, b_idx), _, _ = _resolve_rgb_bands(src)
                if out_shape:
                    r = src.read(r_idx, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                    g = src.read(g_idx, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                    b = src.read(b_idx, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                else:
                    r = src.read(r_idx, window=window)
                    g = src.read(g_idx, window=window)
                    b = src.read(b_idx, window=window)

                r_u8 = normalize_band_percentile(r)
                g_u8 = normalize_band_percentile(g)
                b_u8 = normalize_band_percentile(b)
                rgb_array = np.stack([r_u8, g_u8, b_u8], axis=-1)
                return Image.fromarray(rgb_array, mode="RGB")

            elif n_bands == 2:
                if out_shape:
                    b1 = src.read(1, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                    b2 = src.read(2, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                else:
                    b1 = src.read(1, window=window)
                    b2 = src.read(2, window=window)

                b1_u8 = normalize_band_percentile(b1)
                b2_u8 = normalize_band_percentile(b2)
                eps = 1e-6
                ratio = (b1.astype(np.float32) + eps) / (b2.astype(np.float32) + eps)
                ratio_u8 = normalize_band_percentile(ratio)
                rgb_array = np.stack([b1_u8, b2_u8, ratio_u8], axis=-1)
                return Image.fromarray(rgb_array, mode="RGB")

            else:
                if out_shape:
                    b1 = src.read(1, window=window, out_shape=out_shape, resampling=Resampling.bilinear)
                else:
                    b1 = src.read(1, window=window)

                b1_u8 = normalize_band_percentile(b1)
                rgb_array = np.stack([b1_u8, b1_u8, b1_u8], axis=-1)
                return Image.fromarray(rgb_array, mode="RGB")

    except Exception as exc:
        logger.warning("Failed to read window [%d, %d, %d, %d]: %s", col_off, row_off, width, height, exc)
        return None


def process_geotiff(
    source: Union[bytes, str, Path],
    max_dim: int = 2048,
) -> Tuple[Image.Image, Optional[GeoMetadata]]:
    """
    Decodes raw GeoTIFF or JPEG 2000 (JP2) bytes/file into a normalized 8-bit RGB PIL.Image and
    extracts geospatial metadata (CRS, WGS84 bounding box, Affine transform).

    Uses fast hardware/wavelet decimated sub-sampling for large raster tiles (> max_dim).

    Returns:
        (pil_image, geo_metadata)
    """
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    import pyproj

    try:
        with open_georaster(source) as src:
            n_bands = src.count
            width = src.width
            height = src.height
            crs_obj = src.crs
            transform = src.transform

            # 1. Determine read shape with fast decimation for large tiles
            orig_size = (width, height)
            if max(width, height) > max_dim:
                if width >= height:
                    out_w = max_dim
                    out_h = max(1, int(height * (max_dim / width)))
                else:
                    out_h = max_dim
                    out_w = max(1, int(width * (max_dim / height)))
                read_shape = (out_h, out_w)
                scaled_size = (out_w, out_h)
                scale_x = width / float(out_w)
                scale_y = height / float(out_h)
            else:
                read_shape = None
                scaled_size = orig_size
                scale_x = 1.0
                scale_y = 1.0

            # 2. Read bands with dynamic resolution chain
            band_resolution_tier = None
            band_resolution_warning = None
            if n_bands >= 3:
                (r_idx, g_idx, b_idx), band_resolution_tier, band_resolution_warning = _resolve_rgb_bands(src)
                if read_shape:
                    r = src.read(r_idx, out_shape=read_shape, resampling=Resampling.bilinear)
                    g = src.read(g_idx, out_shape=read_shape, resampling=Resampling.bilinear)
                    b = src.read(b_idx, out_shape=read_shape, resampling=Resampling.bilinear)
                else:
                    r = src.read(r_idx)
                    g = src.read(g_idx)
                    b = src.read(b_idx)

                r_u8 = normalize_band_percentile(r)
                g_u8 = normalize_band_percentile(g)
                b_u8 = normalize_band_percentile(b)
                rgb_array = np.stack([r_u8, g_u8, b_u8], axis=-1)
                pil_img = Image.fromarray(rgb_array, mode="RGB")

            elif n_bands == 2:
                if read_shape:
                    b1 = src.read(1, out_shape=read_shape, resampling=Resampling.bilinear)
                    b2 = src.read(2, out_shape=read_shape, resampling=Resampling.bilinear)
                else:
                    b1 = src.read(1)
                    b2 = src.read(2)

                b1_u8 = normalize_band_percentile(b1)
                b2_u8 = normalize_band_percentile(b2)
                eps = 1e-6
                ratio = (b1.astype(np.float32) + eps) / (b2.astype(np.float32) + eps)
                ratio_u8 = normalize_band_percentile(ratio)
                rgb_array = np.stack([b1_u8, b2_u8, ratio_u8], axis=-1)
                pil_img = Image.fromarray(rgb_array, mode="RGB")
                band_resolution_tier = "sar_dual_polarization"

            else:
                if read_shape:
                    b1 = src.read(1, out_shape=read_shape, resampling=Resampling.bilinear)
                else:
                    b1 = src.read(1)

                b1_u8 = normalize_band_percentile(b1)
                rgb_array = np.stack([b1_u8, b1_u8, b1_u8], axis=-1)
                pil_img = Image.fromarray(rgb_array, mode="RGB")
                band_resolution_tier = "single_band_grayscale"

            # 3. Extract Geospatial Coordinates
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
                    band_resolution_tier=band_resolution_tier,
                    band_resolution_warning=band_resolution_warning,
                )

            return pil_img, geo_meta

    except Exception as e:
        logger.warning("Rasterio GeoTIFF/JP2 extraction failed: %s. Falling back to PIL.", e)
        if isinstance(source, (str, Path)):
            img = Image.open(source).convert("RGB")
        else:
            buf = io.BytesIO(source)
            img = Image.open(buf).convert("RGB")
        if max(img.width, img.height) > max_dim:
            if img.width >= img.height:
                nw = max_dim
                nh = int(img.height * (max_dim / img.width))
            else:
                nh = max_dim
                nw = int(img.width * (max_dim / img.height))
            img = img.resize((nw, nh), Image.Resampling.BICUBIC)
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

    raw_w, raw_h = geo_meta.raw_size
    # Determine if input boxes are in [0, 1000] normalized space
    is_normalized_1000 = False
    if pixel_boxes:
        max_coord = max(max(b[:4]) for b in pixel_boxes if len(b) >= 4)
        if max_coord <= 1000 and max(raw_w, raw_h) > 1000:
            is_normalized_1000 = True

    for box in pixel_boxes:
        if len(box) < 4:
            continue
        px1, py1, px2, py2 = box[:4]

        if is_normalized_1000:
            rx1, ry1 = (px1 / 1000.0) * raw_w, (py1 / 1000.0) * raw_h
            rx2, ry2 = (px2 / 1000.0) * raw_w, (py2 / 1000.0) * raw_h
        else:
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
