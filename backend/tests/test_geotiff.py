"""
Unit tests for GeoTIFF processing and coordinate projection.
"""

import io
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from PIL import Image

from app.geotiff import (
    GeoMetadata,
    is_geotiff,
    normalize_band_percentile,
    pixel_boxes_to_geo_polygons,
    process_geotiff,
)


def _create_synthetic_geotiff_bytes(
    width: int = 100,
    height: int = 100,
    n_bands: int = 3,
    dtype=np.uint16,
    bounds=(12.0, 48.0, 12.1, 48.1),
    crs="EPSG:4326",
) -> bytes:
    """Creates an in-memory GeoTIFF bytes buffer."""
    min_x, min_y, max_x, max_y = bounds
    transform = from_bounds(min_x, min_y, max_x, max_y, width, height)

    with rasterio.io.MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=height,
            width=width,
            count=n_bands,
            dtype=dtype,
            crs=crs,
            transform=transform,
        ) as dst:
            for i in range(1, n_bands + 1):
                if np.issubdtype(dtype, np.floating):
                    data = np.random.uniform(0.01, 1.0, size=(height, width)).astype(dtype)
                else:
                    data = np.random.randint(100, 8000, size=(height, width), dtype=dtype)
                dst.write(data, i)

        return memfile.read()


class TestGeoTIFFDetectionAndProcessing:
    """Test GeoTIFF magic byte check and band decoding."""

    def test_magic_byte_detection(self):
        tiff_bytes = _create_synthetic_geotiff_bytes()
        assert is_geotiff(tiff_bytes) is True
        assert is_geotiff(b"PNG\r\n\x1a\n") is False
        assert is_geotiff(b"") is False

    def test_normalize_band_percentile(self):
        raw_band = np.linspace(0, 10000, 1000).reshape((10, 100))
        stretched = normalize_band_percentile(raw_band, p_low=2.0, p_high=98.0)
        assert stretched.dtype == np.uint8
        assert stretched.min() == 0
        assert stretched.max() == 255

    def test_process_optical_geotiff(self):
        tiff_bytes = _create_synthetic_geotiff_bytes(
            width=64, height=64, n_bands=4, dtype=np.uint16,
            bounds=(12.5, 48.5, 12.6, 48.6), crs="EPSG:4326",
        )
        img, geo_meta = process_geotiff(tiff_bytes)
        assert isinstance(img, Image.Image)
        assert img.size == (64, 64)
        assert img.mode == "RGB"

        assert geo_meta is not None
        assert geo_meta.crs == "EPSG:4326"
        assert len(geo_meta.image_bounds) == 4
        assert geo_meta.image_bounds[0] == pytest.approx(12.5, abs=0.01)
        assert geo_meta.image_bounds[1] == pytest.approx(48.5, abs=0.01)

    def test_process_sar_geotiff(self):
        tiff_bytes = _create_synthetic_geotiff_bytes(
            width=50, height=50, n_bands=1, dtype=np.float32,
            bounds=(10.0, 50.0, 10.1, 50.1), crs="EPSG:4326",
        )
        img, geo_meta = process_geotiff(tiff_bytes)
        assert isinstance(img, Image.Image)
        assert img.size == (50, 50)
        assert geo_meta is not None
        assert geo_meta.image_bounds[0] == pytest.approx(10.0, abs=0.01)


class TestCoordinateProjection:
    """Test converting pixel boxes to GeoJSON polygons."""

    def test_pixel_to_geo_polygons(self):
        geo_meta = GeoMetadata(
            crs="EPSG:4326",
            image_bounds=[10.0, 50.0, 10.1, 50.1],
            affine_transform=(0.001, 0.0, 10.0, 0.0, -0.001, 50.1),
            raw_size=(100, 100),
            scaled_size=(100, 100),
            scale_factor=(1.0, 1.0),
        )

        boxes = [[10, 10, 50, 50]]
        polys = pixel_boxes_to_geo_polygons(boxes, geo_meta)
        assert len(polys) == 1
        poly = polys[0]
        # Polygon should have 5 vertices (closed ring)
        assert len(poly) == 5
        assert poly[0] == poly[-1]
        # Coordinates should lie within image bounds
        for pt in poly:
            assert 10.0 <= pt[0] <= 10.1
            assert 50.0 <= pt[1] <= 50.1


class TestDynamicBandResolution:
    """Tests for metadata-aware band selection tiers in process_geotiff."""

    def test_tier1_colorinterp_explicit(self):
        """Tier 1: Verify src.colorinterp resolves custom BGR band arrangements."""
        from rasterio.enums import ColorInterp
        width, height = 32, 32
        transform = from_bounds(10.0, 40.0, 10.1, 40.1, width, height)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=4,
                dtype=np.uint8,
                crs="EPSG:4326",
                transform=transform,
            ) as dst:
                # Set inverted order: 1: Blue, 2: Green, 3: Red, 4: Alpha
                dst.colorinterp = (ColorInterp.blue, ColorInterp.green, ColorInterp.red, ColorInterp.alpha)
                dst.write(np.full((height, width), 200, dtype=np.uint8), 1)  # Blue = 200
                dst.write(np.full((height, width), 100, dtype=np.uint8), 2)  # Green = 100
                dst.write(np.full((height, width), 50, dtype=np.uint8), 3)   # Red = 50
                dst.write(np.full((height, width), 255, dtype=np.uint8), 4)

            raw_bytes = memfile.read()

        img, geo_meta = process_geotiff(raw_bytes)
        assert geo_meta is not None
        assert geo_meta.band_resolution_tier == "colorinterp"
        # In the output RGB image, Red channel should be 50, Green 100, Blue 200
        arr = np.array(img)
        assert arr[0, 0, 0] == 0 or arr[0, 0, 0] <= 128  # Red was band 3 (50)
        assert arr[0, 0, 2] == 255 or arr[0, 0, 2] >= 128 # Blue was band 1 (200)

    def test_tier2_band_descriptions_sentinel_names(self):
        """Tier 2: Verify B04/B03/B02 band descriptions resolve correctly."""
        width, height = 32, 32
        transform = from_bounds(10.0, 40.0, 10.1, 40.1, width, height)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=4,
                dtype=np.uint8,
                crs="EPSG:4326",
                transform=transform,
                photometric="MINISBLACK",
            ) as dst:
                dst.set_band_description(1, "B02 - Blue")
                dst.set_band_description(2, "B03 - Green")
                dst.set_band_description(3, "B04 - Red")
                dst.set_band_description(4, "B08 - NIR")
                for i in range(1, 5):
                    dst.write(np.full((height, width), i * 50, dtype=np.uint8), i)

            raw_bytes = memfile.read()

        img, geo_meta = process_geotiff(raw_bytes)
        assert geo_meta is not None
        assert geo_meta.band_resolution_tier == "band_description_match"

    def test_tier2_band_descriptions_case_tolerance(self):
        """Tier 2: Verify case-insensitive red/green/blue descriptions resolve correctly."""
        width, height = 32, 32
        transform = from_bounds(10.0, 40.0, 10.1, 40.1, width, height)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=3,
                dtype=np.uint8,
                crs="EPSG:4326",
                transform=transform,
                photometric="MINISBLACK",
            ) as dst:
                dst.set_band_description(1, "RED (Channel 1)")
                dst.set_band_description(2, "GREEN (Channel 2)")
                dst.set_band_description(3, "BLUE (Channel 3)")
                for i in range(1, 4):
                    dst.write(np.full((height, width), i * 60, dtype=np.uint8), i)

            raw_bytes = memfile.read()

        img, geo_meta = process_geotiff(raw_bytes)
        assert geo_meta is not None
        assert geo_meta.band_resolution_tier == "band_description_match"

    def test_tier3_sentinel2_full_stack_heuristic(self):
        """Tier 3: 12-band GeoTIFF with no tags triggers Sentinel-2 (4, 3, 2) mapping."""
        width, height = 16, 16
        transform = from_bounds(10.0, 40.0, 10.1, 40.1, width, height)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=12,
                dtype=np.uint8,
                crs="EPSG:4326",
                transform=transform,
                photometric="MINISBLACK",
            ) as dst:
                for i in range(1, 13):
                    dst.write(np.full((height, width), i * 15, dtype=np.uint8), i)

            raw_bytes = memfile.read()

        img, geo_meta = process_geotiff(raw_bytes)
        assert geo_meta is not None
        assert geo_meta.band_resolution_tier == "sentinel2_full_stack_heuristic"
        assert geo_meta.band_resolution_warning is None

    def test_tier4_default_standard_stack(self):
        """Tier 4: Standard 3/4-band GeoTIFF defaults to (1, 2, 3) with warning."""
        width, height = 16, 16
        transform = from_bounds(10.0, 40.0, 10.1, 40.1, width, height)

        with rasterio.io.MemoryFile() as memfile:
            with memfile.open(
                driver="GTiff",
                height=height,
                width=width,
                count=4,
                dtype=np.uint8,
                crs="EPSG:4326",
                transform=transform,
                photometric="MINISBLACK",
            ) as dst:
                for i in range(1, 5):
                    dst.write(np.full((height, width), i * 40, dtype=np.uint8), i)

            raw_bytes = memfile.read()

        img, geo_meta = process_geotiff(raw_bytes)
        assert geo_meta is not None
        assert geo_meta.band_resolution_tier == "default_123"
        assert geo_meta.band_resolution_warning is not None
        assert "No photometric or band description" in geo_meta.band_resolution_warning
