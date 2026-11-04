"""
Upload fuzz and security tests for POST /api/v1/upload and the /assets routes.

Every malformed or hostile upload must end in a clean 4xx (never a 500), leave no file
on disk and no database row, and never let the client choose where or as what the file
is stored. The mutation fuzz is seeded, so a failure reproduces exactly.
"""

from __future__ import annotations

import base64
import io
import random
import struct
import time
import zlib

import numpy as np
import pytest
import rasterio
import rasterio.transform
from PIL import Image

from app.config import UPLOADS_DIR

from .conftest import register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _png(w: int = 64, h: int = 48) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.random.default_rng(0).integers(0, 255, (h, w, 3), dtype=np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def _jpeg(w: int = 64, h: int = 48) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (h, w, 3), dtype=np.uint8)).save(buf, "JPEG")
    return buf.getvalue()


def _geotiff(w: int = 64, h: int = 48) -> bytes:
    arr = np.random.default_rng(2).integers(10, 240, (3, h, w), dtype=np.uint8)
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="GTiff", width=w, height=h, count=3, dtype="uint8", crs="EPSG:4326",
                       transform=rasterio.transform.from_bounds(77.0, 28.0, 77.1, 28.1, w, h)) as dst:
        dst.write(arr)
    return buf.getvalue()


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _png_bomb(w: int, h: int) -> bytes:
    """A tiny PNG whose header claims w x h pixels: 1-bit grey, all-zero rows, deflated to almost nothing."""
    row = b"\x00" + b"\x00" * ((w + 7) // 8)
    comp = zlib.compressobj(9)
    idat = b"".join(comp.compress(row) for _ in range(h)) + comp.flush()
    ihdr = struct.pack(">IIBBBBB", w, h, 1, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def _tiff_header_claiming(w: int, h: int) -> bytes:
    """A minimal little-endian TIFF whose IFD claims w x h pixels but carries almost no strip data."""
    entries = [
        (256, 4, 1, w),        # ImageWidth (LONG)
        (257, 4, 1, h),        # ImageLength
        (258, 3, 1, 8),        # BitsPerSample
        (259, 3, 1, 1),        # Compression: none
        (262, 3, 1, 1),        # Photometric: BlackIsZero
        (273, 4, 1, 8 + 2 + 12 * 9 + 4),  # StripOffsets -> just past the IFD
        (277, 3, 1, 1),        # SamplesPerPixel
        (278, 4, 1, h),        # RowsPerStrip
        (279, 4, 1, w * h),    # StripByteCounts (a lie: the file ends right after)
    ]
    ifd = struct.pack("<H", len(entries))
    for tag, typ, count, value in entries:
        ifd += struct.pack("<HHI", tag, typ, count) + (struct.pack("<HH", value, 0) if typ == 3 else struct.pack("<I", value))
    ifd += struct.pack("<I", 0)
    return b"II*\x00" + struct.pack("<I", 8) + ifd + b"\x00" * 64


def _upload(client, data: bytes, name: str = "scene.tif", ctype: str = "application/octet-stream"):
    return client.post("/api/v1/upload", files={"file": (name, data, ctype)})


def _files_on_disk(user_dir) -> list:
    return sorted(p.name for p in user_dir.iterdir()) if user_dir.exists() else []


@pytest.fixture
def user(sync_client):
    """(client, headers, user_dir) for a fresh user, so disk and quota checks see only this test's files."""
    headers, body = register_user(sync_client)
    sync_client.headers.update(headers)
    return sync_client, headers, UPLOADS_DIR / body["user"]["id"]


def _assert_rejected_cleanly(client, user_dir, res, before_files, before_count):
    assert 400 <= res.status_code < 500, (res.status_code, res.text[:300])
    body = res.json()
    assert body["error"]["code"] in {"UNSUPPORTED_FORMAT", "PAYLOAD_TOO_LARGE", "QUOTA_EXCEEDED", "VALIDATION_ERROR"}
    assert "Traceback" not in res.text and "File \"" not in res.text
    assert _files_on_disk(user_dir) == before_files, "a rejected upload left a file behind"
    assert client.get("/api/v1/storage").json()["asset_count"] == before_count, "a rejected upload left a row"


# ---------------------------------------------------------------------------
# Wrong or hostile content types
# ---------------------------------------------------------------------------
NOT_IMAGES = {
    "empty": b"",
    "html": b"<!doctype html><script>alert(1)</script>",
    "svg": b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
    "pdf": b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF",
    "zip": b"PK\x03\x04" + b"\x00" * 60,
    "windows exe": b"MZ\x90\x00" + b"\x00" * 60,
    "elf": b"\x7fELF\x02\x01\x01" + b"\x00" * 60,
    "gif": b"GIF89a\x01\x00\x01\x00\x00\x00\x00;",
    "bmp": b"BM" + b"\x00" * 60,
    "webp": b"RIFF\x00\x00\x00\x00WEBPVP8 ",
    "nul bytes": b"\x00" * 4096,
    "text with tif name": b"definitely not a tiff",
}


@pytest.mark.parametrize("label", list(NOT_IMAGES))
def test_non_image_payloads_are_rejected(user, label):
    client, _, user_dir = user
    res = _upload(client, NOT_IMAGES[label], name="scene.tif", ctype="image/tiff")
    _assert_rejected_cleanly(client, user_dir, res, [], 0)
    assert res.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


@pytest.mark.parametrize("label,data", [
    ("png magic + garbage", b"\x89PNG\r\n\x1a\n" + b"\xde\xad\xbe\xef" * 64),
    ("tiff magic + garbage", b"II*\x00" + b"\xff" * 256),
    ("bigtiff magic + garbage", b"II+\x00" + b"\x01" * 256),
    ("big-endian tiff + garbage", b"MM\x00*" + b"\x7f" * 256),
    ("jpeg magic + garbage", b"\xff\xd8\xff\xe0" + b"\x00" * 256),
    ("jp2 box + garbage", b"\x00\x00\x00\x0cjP  \r\n\x87\n" + b"\x13" * 256),
    ("j2k codestream + garbage", b"\xff\x4f\xff\x51" + b"\x00" * 256),
    ("magic only", b"\x89PNG\r\n\x1a\n"),
])
def test_magic_bytes_with_a_broken_body_are_rejected(user, label, data):
    client, _, user_dir = user
    res = _upload(client, data)
    _assert_rejected_cleanly(client, user_dir, res, [], 0)


def test_type_comes_from_magic_bytes_not_the_name_or_content_type(user):
    """A PNG named evil.exe and labelled text/html is stored as .png and served as an attachment."""
    client, _, user_dir = user
    res = _upload(client, _png(), name="evil.exe", ctype="text/html")
    assert res.status_code == 200, res.text
    j = res.json()
    assert j["format"] == "standard"
    assert _files_on_disk(user_dir) == [f"{j['asset_id']}.png"]
    got = client.get(j["url"])
    assert got.status_code == 200
    assert got.headers["x-content-type-options"] == "nosniff"
    assert got.headers["content-disposition"].startswith("attachment")
    assert "text/html" not in got.headers["content-type"]


def test_jpeg_and_geotiff_round_trip(user):
    client, _, user_dir = user
    for data, ext in ((_jpeg(), ".jpg"), (_geotiff(), ".tif")):
        res = _upload(client, data, name="x" + ext)
        assert res.status_code == 200, res.text
        assert (user_dir / f"{res.json()['asset_id']}{ext}").is_file()
        assert client.get(res.json()["url"]).content == data


# ---------------------------------------------------------------------------
# Hostile filenames
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("../../../../etc/passwd.png", "passwd.png"),
    ("..\\..\\Windows\\win.ini.png", "win.ini.png"),
    ("C:\\Users\\victim\\scene.png", "scene.png"),
    ("/abs/path/scene.png", "scene.png"),
    ("dir/", "upload"),
    ("", None),  # multipart with an empty filename: FastAPI may reject it (422) or keep the default
    ("<img src=x onerror=alert(1)>.png", "<img src=x onerror=alert(1)>.png"),
    ("scene\u202egnp.exe", "scene\u202egnp.exe"),
])
def test_hostile_filenames_never_choose_the_storage_path(user, name, expected):
    client, _, user_dir = user
    res = _upload(client, _png(), name=name)
    if expected is None:
        assert res.status_code in (200, 422), res.text
        if res.status_code != 200:
            return
    else:
        assert res.status_code == 200, res.text
    j = res.json()
    if expected is not None:
        assert j["filename"] == expected
    assert "/" not in j["filename"] and "\\" not in j["filename"]
    # Stored under the user's directory by asset id only, whatever the client called it
    assert _files_on_disk(user_dir) == [f"{j['asset_id']}.png"]
    assert not any(p.name.endswith("passwd.png") for p in UPLOADS_DIR.parent.rglob("*passwd*"))


def test_very_long_filename_is_truncated(user):
    client, _, user_dir = user
    res = _upload(client, _png(), name="a" * 300 + ".png")
    assert res.status_code == 200, res.text
    assert len(res.json()["filename"]) == 255
    # Far past any sane header size the multipart parser refuses the part outright: a clean 400
    before = _files_on_disk(user_dir)
    res = _upload(client, _png(), name="a" * 5000 + ".png")
    assert res.status_code in (200, 400), res.text
    if res.status_code == 400:
        _assert_rejected_cleanly(client, user_dir, res, before, 1)


# ---------------------------------------------------------------------------
# Decompression bombs and lying headers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("w,h", [(30_000, 30_000), (65_000, 65_000)])
def test_png_decompression_bomb_is_bounded(user, w, h):
    """A ~100 KB PNG claiming up to 4.2 gigapixels: rejected or decimated quickly, never decoded at full size."""
    client, _, user_dir = user
    data = _png_bomb(w, h)
    assert len(data) < 2_000_000
    t0 = time.perf_counter()
    res = _upload(client, data, name="bomb.png")
    elapsed = time.perf_counter() - t0
    assert elapsed < 60, f"bomb took {elapsed:.1f}s"
    if w * h <= 1024 * 1_000_000:  # under the default MAX_IMAGE_MEGAPIXELS: decimated, not decoded
        assert res.status_code == 200, res.text
        j = res.json()
        assert (j["width"], j["height"]) == (w, h)
        preview = Image.open(io.BytesIO(base64.b64decode(j["preview_base64"].split(",", 1)[1])))
        assert max(preview.size) <= 1024
    else:  # refused from the header alone, so it is fast
        assert res.status_code == 413, res.text
        assert "MAX_IMAGE_MEGAPIXELS" in res.json()["error"]["message"]
        assert elapsed < 2, f"rejection took {elapsed:.1f}s; the header check should precede any decode"
        _assert_rejected_cleanly(client, user_dir, res, [], 0)


def test_pixel_limit_is_configurable(user, monkeypatch):
    from app.config import settings
    client, _, user_dir = user
    monkeypatch.setattr(settings, "max_image_megapixels", 1)
    res = _upload(client, _png(1200, 1000), name="1.2mp.png")
    assert res.status_code == 413
    _assert_rejected_cleanly(client, user_dir, res, [], 0)
    monkeypatch.setattr(settings, "max_image_megapixels", 0)  # 0 = unlimited
    assert _upload(client, _png(1200, 1000), name="1.2mp.png").status_code == 200


def test_tiff_header_claiming_huge_dimensions_with_no_data(user):
    client, _, user_dir = user
    res = _upload(client, _tiff_header_claiming(60_000, 60_000))  # 3.6 gigapixels, ~200 bytes
    assert res.status_code == 413, res.text
    _assert_rejected_cleanly(client, user_dir, res, [], 0)


def test_base64_query_bomb_is_a_400(user):
    """The same guard covers GeoTIFFs sent inline to /query instead of uploaded."""
    client, _, _ = user
    data = base64.b64encode(_tiff_header_claiming(60_000, 60_000)).decode()
    res = client.post("/api/v1/query", json={
        "query": "Describe this image.",
        "images": [{"id": "a", "modality": "optical", "url_or_base64": data}]})
    assert res.status_code == 400, res.text
    assert "MAX_IMAGE_MEGAPIXELS" in res.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Seeded mutation fuzz
# ---------------------------------------------------------------------------
def _mutate(data: bytes, rng: random.Random) -> bytes:
    b = bytearray(data)
    op = rng.choice(["flip", "truncate", "splice", "zero_run", "dup"])
    if op == "flip":
        for _ in range(rng.randint(1, 32)):
            i = rng.randrange(8, len(b))  # keep the magic so the decoder, not the sniffer, sees it
            b[i] ^= 1 << rng.randrange(8)
    elif op == "truncate":
        b = b[: rng.randrange(8, len(b))]
    elif op == "splice":
        i = rng.randrange(8, len(b))
        b[i:i] = bytes(rng.randrange(256) for _ in range(rng.randint(1, 512)))
    elif op == "zero_run":
        i = rng.randrange(8, len(b))
        b[i: i + rng.randint(1, 256)] = b"\x00" * min(256, len(b) - i)
    else:
        i, j = sorted(rng.randrange(8, len(b)) for _ in range(2))
        b[j:j] = b[i:j]
    return bytes(b)


SEEDS = range(24)


@pytest.mark.parametrize("fmt", ["png", "jpeg", "geotiff"])
def test_mutation_fuzz_never_500s_or_leaks_files(user, fmt):
    client, _, user_dir = user
    base = {"png": _png, "jpeg": _jpeg, "geotiff": _geotiff}[fmt]()
    accepted = 0
    for seed in SEEDS:
        rng = random.Random(f"{fmt}-{seed}")
        data = _mutate(base, rng)
        before_files = _files_on_disk(user_dir)
        before_count = client.get("/api/v1/storage").json()["asset_count"]
        res = _upload(client, data, name=f"fuzz-{seed}.bin")
        assert res.status_code in (200, 400), f"seed {fmt}-{seed}: {res.status_code} {res.text[:200]}"
        if res.status_code == 200:
            accepted += 1
            j = res.json()
            assert j["width"] > 0 and j["height"] > 0
            # The preview route must also cope with whatever was accepted
            assert client.get(f"/api/v1/assets/{j['asset_id']}/preview").status_code in (200, 404)
        else:
            _assert_rejected_cleanly(client, user_dir, res, before_files, before_count)
    # Not an assertion on decoder leniency, just a record for the log
    print(f"{fmt}: {accepted}/{len(SEEDS)} mutants decoded")


# ---------------------------------------------------------------------------
# Request shape and access control
# ---------------------------------------------------------------------------
def test_upload_requires_auth(sync_client):
    res = _upload(sync_client, _png())
    assert res.status_code == 401


def test_missing_file_field_is_422_not_500(user):
    client, _, _ = user
    res = client.post("/api/v1/upload", files={"not_file": ("a.png", _png(), "image/png")})
    assert res.status_code == 422
    res = client.post("/api/v1/upload", data={"file": "just a string"})
    assert res.status_code == 422


def test_size_limit_stops_mid_stream_and_cleans_up(user, monkeypatch):
    from app.config import settings
    client, _, user_dir = user
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    data = _png() + b"\x00" * (2 * 1024 * 1024)
    res = _upload(client, data, name="big.png")
    assert res.status_code == 413
    _assert_rejected_cleanly(client, user_dir, res, [], 0)


@pytest.mark.parametrize("asset_id", [
    "../../etc/passwd", "..%2F..%2Fsatquery.db", "not-a-uuid", "00000000-0000-0000-0000-000000000000",
    "%00", "' OR '1'='1",
])
def test_asset_routes_reject_bad_ids(user, asset_id):
    client, _, _ = user
    for path in (f"/api/v1/assets/{asset_id}", f"/api/v1/assets/{asset_id}/preview"):
        res = client.get(path)
        assert res.status_code in (404, 405, 422), (path, res.status_code)
    assert client.delete(f"/api/v1/assets/{asset_id}").status_code in (404, 405, 422)


def test_other_users_cannot_read_preview_or_delete(sync_client):
    ha, _ = register_user(sync_client)
    hb, _ = register_user(sync_client)
    res = sync_client.post("/api/v1/upload", headers=ha, files={"file": ("a.png", _png(), "image/png")})
    aid = res.json()["asset_id"]
    for method, path in (("get", f"/api/v1/assets/{aid}"), ("get", f"/api/v1/assets/{aid}/preview"),
                         ("delete", f"/api/v1/assets/{aid}")):
        assert getattr(sync_client, method)(path, headers=hb).status_code == 404
    assert sync_client.get(f"/api/v1/assets/{aid}", headers=ha).status_code == 200
