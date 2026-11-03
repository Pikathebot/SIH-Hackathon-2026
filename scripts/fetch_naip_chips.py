"""Cut real high-resolution sample chips from USDA NAIP aerial imagery (public domain).

    .venv\\Scripts\\python scripts\\fetch_naip_chips.py

NAIP is ~0.6 m RGB(+NIR) imagery hosted as Cloud-Optimized GeoTIFFs on the Microsoft
Planetary Computer. Only the window around each target is downloaded. The chips replace the
synthetic airbase/port samples, which had no real objects for detection to find.
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[1]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"
SIZE = 1024  # pixels; ~600 m on a side at 0.6 m

# name -> (lon, lat, description)
TARGETS = {
    "optical/naip_airbase_davis_monthan.tif": (
        -110.8445, 32.1500,
        "NAIP 0.6 m RGB, Davis-Monthan AFB aircraft storage (AMARG), Tucson AZ: rows of parked aircraft",
    ),
    "optical/naip_port_long_beach.tif": (
        -118.2140, 33.7560,
        "NAIP 0.6 m RGB, Port of Long Beach container terminal, CA: berthed ships, gantry cranes, containers",
    ),
}


def _get(url: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def latest_item(lon: float, lat: float) -> dict:
    res = _get(STAC, {"collections": ["naip"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
                      "limit": 50})
    items = sorted(res["features"], key=lambda f: f["properties"]["datetime"], reverse=True)
    if not items:
        raise SystemExit(f"no NAIP item at {lon},{lat}")
    return items[0]


def main() -> None:
    token = _get(TOKEN)["token"]
    for rel, (lon, lat, desc) in TARGETS.items():
        item = latest_item(lon, lat)
        href = f"{item['assets']['image']['href']}?{token}"
        dst = ROOT / "sample_data" / rel
        with rasterio.open(href) as src:
            xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
            row, col = src.index(xs[0], ys[0])
            win = Window(col - SIZE // 2, row - SIZE // 2, SIZE, SIZE)
            data = src.read([1, 2, 3], window=win, boundless=False)
            profile = src.profile.copy()
            profile.update(driver="GTiff", count=3, width=SIZE, height=SIZE,
                           transform=src.window_transform(win), compress="deflate", predictor=2,
                           tiled=False, photometric="RGB")
            profile.pop("blockxsize", None)
            profile.pop("blockysize", None)
        date = item["properties"]["datetime"][:10]
        with rasterio.open(dst, "w", **profile) as out:
            out.write(data)
            out.update_tags(SOURCE="USDA NAIP via Microsoft Planetary Computer (public domain)",
                            NAIP_ITEM=item["id"], ACQUISITION_DATE=date, DESCRIPTION=desc)
            for i, name in enumerate(["red", "green", "blue"], 1):
                out.set_band_description(i, name)
        print(f"{rel}: {item['id']} ({date}) {dst.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
