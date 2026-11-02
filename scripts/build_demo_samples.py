"""Copy the sample images used by the UI's "Sample Questions" presets into
frontend/public/samples/, losslessly DEFLATE-compressed so the frontend bundle stays small.

    .venv\\Scripts\\python scripts\\build_demo_samples.py

Pixels, CRS and transform are unchanged; only the TIFF compression differs.
"""
import shutil
from pathlib import Path

import rasterio

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "sample_data"
DST = ROOT / "frontend" / "public" / "samples"

# Keep in sync with DEMO_PRESETS in frontend/src/components/DemoPresetSelector.tsx
FILES = [
    "optical/real_sentinel2_austria_tci.tif",
    "optical/optical_port_rotterdam.tif",
    "optical/optical_sentinel2_lake.jp2",
    "bitemporal_change/urban_expansion_t1_2021.tif",
    "bitemporal_change/urban_expansion_t2_2024.tif",
    "cross_modal_fusion/cloudy_optical_scene.tif",
    "cross_modal_fusion/penetrating_sar_scene.tif",
]


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        src = SRC / rel
        dst = DST / src.name
        if src.suffix.lower() != ".tif":
            shutil.copyfile(src, dst)
        else:
            with rasterio.open(src) as d:
                profile = d.profile.copy()
                profile.update(compress="deflate", predictor=2, tiled=False)
                data = d.read()
                tags = d.tags()
                with rasterio.open(dst, "w", **profile) as out:
                    out.write(data)
                    out.update_tags(**tags)
                    for i in range(1, d.count + 1):
                        if d.descriptions[i - 1]:
                            out.set_band_description(i, d.descriptions[i - 1])
            with rasterio.open(src) as a, rasterio.open(dst) as b:
                assert (a.read() == b.read()).all() and a.crs == b.crs and a.transform == b.transform, rel
        print(f"{dst.name:40s} {src.stat().st_size / 1e6:5.2f} MB -> {dst.stat().st_size / 1e6:5.2f} MB")


if __name__ == "__main__":
    main()
