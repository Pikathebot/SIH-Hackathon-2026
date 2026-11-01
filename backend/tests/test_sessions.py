"""Sessions, history, owned uploads and image-source safety (API_CONTRACT.md v2.0.0 §5)."""

import base64
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import DATA_DIR, settings
from app.main import app
from tests.conftest import register_user


def _png_bytes(color=(30, 90, 160), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _png_b64() -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()


@pytest.fixture
def two_users():
    with TestClient(app) as anon:
        a, _ = register_user(anon)
        b, _ = register_user(anon)
    with TestClient(app, headers=a) as ca, TestClient(app, headers=b) as cb:
        yield ca, cb


def _upload(client, data=None, name="scene.png"):
    res = client.post("/api/v1/upload", files={"file": (name, data or _png_bytes(), "application/octet-stream")})
    assert res.status_code == 200, res.text
    return res.json()


# ── Sessions CRUD ────────────────────────────────────────────────────────
def test_session_crud(authed_client):
    c = authed_client
    created = c.post("/api/v1/sessions", json={"title": "Rotterdam port"})
    assert created.status_code == 201
    sid = created.json()["id"]
    assert c.post("/api/v1/sessions").json()["title"] == "New analysis"  # body optional

    renamed = c.patch(f"/api/v1/sessions/{sid}", json={"title": "Port of Rotterdam"})
    assert renamed.status_code == 200 and renamed.json()["title"] == "Port of Rotterdam"
    listed = c.get("/api/v1/sessions").json()
    assert listed[0]["id"] == sid  # most recently updated first
    assert c.get(f"/api/v1/sessions/{sid}").json()["query_count"] == 0

    assert c.delete(f"/api/v1/sessions/{sid}").status_code == 204
    assert c.get(f"/api/v1/sessions/{sid}").status_code == 404


def test_users_cannot_see_each_others_sessions(two_users):
    a, b = two_users
    sid = a.post("/api/v1/sessions", json={"title": "A's work"}).json()["id"]
    assert all(s["id"] != sid for s in b.get("/api/v1/sessions").json())
    for method, path, kw in [("get", f"/api/v1/sessions/{sid}", {}),
                             ("get", f"/api/v1/sessions/{sid}/queries", {}),
                             ("patch", f"/api/v1/sessions/{sid}", {"json": {"title": "mine now"}}),
                             ("delete", f"/api/v1/sessions/{sid}", {})]:
        res = getattr(b, method)(path, **kw)
        assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND", (method, path)
    assert a.get(f"/api/v1/sessions/{sid}").json()["title"] == "A's work"


# ── Upload → query by asset_id → history ─────────────────────────────────
def test_upload_query_by_asset_and_history_round_trip(authed_client):
    c = authed_client
    sid = c.post("/api/v1/sessions", json={"title": "History"}).json()["id"]
    asset = _upload(c)

    res = c.post("/api/v1/query", json={
        "query": "What is in this image?", "session_id": sid,
        "images": [{"id": "img1", "modality": "optical", "asset_id": asset["asset_id"]}],
    })
    assert res.status_code == 200, res.text
    answer = res.json()

    # The legacy asset-URL form still works for the same owner
    res2 = c.post("/api/v1/query", json={
        "query": "Highlight the water bodies in this image.", "session_id": sid,
        "images": [{"id": "img1", "modality": "optical", "url_or_base64": asset["url"]}],
    })
    assert res2.status_code == 200, res2.text

    history = c.get(f"/api/v1/sessions/{sid}/queries").json()
    assert [h["query_text"] for h in history] == ["What is in this image?", "Highlight the water bodies in this image."]
    assert history[0]["image_asset_ids"] == [asset["asset_id"]]
    assert history[0]["response"] == answer  # re-renders exactly what was returned
    assert history[1]["response"]["visual_evidence"] == res2.json()["visual_evidence"]
    assert c.get(f"/api/v1/sessions/{sid}").json()["query_count"] == 2

    # Deleting the session removes its queries and evidence files, but keeps the uploaded asset.
    evidence_files = list((DATA_DIR / "evidence").rglob("*.json"))
    assert c.delete(f"/api/v1/sessions/{sid}").status_code == 204
    assert len(list((DATA_DIR / "evidence").rglob("*.json"))) == len(evidence_files) - 2
    assert c.get(f"/api/v1/assets/{asset['asset_id']}").status_code == 200


def test_inline_base64_images_are_saved_as_assets_for_history(authed_client):
    c = authed_client
    sid = c.post("/api/v1/sessions").json()["id"]
    res = c.post("/api/v1/query", json={"query": "Describe this scene.", "session_id": sid,
                                        "images": [{"id": "img1", "modality": "optical", "url_or_base64": _png_b64()}]})
    assert res.status_code == 200
    (entry,) = c.get(f"/api/v1/sessions/{sid}/queries").json()
    (asset_id,) = entry["image_asset_ids"]
    img = c.get(f"/api/v1/assets/{asset_id}")
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_query_without_session_is_not_in_any_history(authed_client):
    c = authed_client
    sid = c.post("/api/v1/sessions").json()["id"]
    res = c.post("/api/v1/query", json={"query": "Describe this scene.",
                                        "images": [{"id": "img1", "modality": "optical", "url_or_base64": _png_b64()}]})
    assert res.status_code == 200
    assert c.get(f"/api/v1/sessions/{sid}/queries").json() == []


# ── Ownership of assets and sessions in queries ──────────────────────────
def test_users_cannot_use_or_read_each_others_assets(two_users):
    a, b = two_users
    asset = _upload(a)
    assert b.get(f"/api/v1/assets/{asset['asset_id']}").status_code == 404
    for image in ({"asset_id": asset["asset_id"]}, {"url_or_base64": asset["url"]}):
        res = b.post("/api/v1/query", json={"query": "Describe this scene.",
                                            "images": [{"id": "img1", "modality": "optical", **image}]})
        assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


def test_query_into_someone_elses_session_is_404(two_users):
    a, b = two_users
    sid = a.post("/api/v1/sessions").json()["id"]
    res = b.post("/api/v1/query", json={"query": "Describe this scene.", "session_id": sid,
                                        "images": [{"id": "img1", "modality": "optical", "url_or_base64": _png_b64()}]})
    assert res.status_code == 404
    assert a.get(f"/api/v1/sessions/{sid}/queries").json() == []


def test_image_needs_exactly_one_source(authed_client):
    for image in ({}, {"url_or_base64": _png_b64(), "asset_id": str(uuid.uuid4())}):
        res = authed_client.post("/api/v1/query", json={"query": "Describe.",
                                                        "images": [{"id": "i", "modality": "optical", **image}]})
        assert res.status_code == 422


# ── Upload validation ────────────────────────────────────────────────────
def test_upload_rejects_non_images_by_content_not_extension(authed_client):
    res = authed_client.post("/api/v1/upload", files={"file": ("scene.tif", b"MZ\x90\x00 not an image", "image/tiff")})
    assert res.status_code == 400 and res.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_size_limit(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_mb", 0)
    res = authed_client.post("/api/v1/upload", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert res.status_code == 413 and res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_uploads_are_stored_per_user(authed_client):
    asset = _upload(authed_client)
    me = authed_client.get("/api/v1/auth/me").json()
    assert list((DATA_DIR / "uploads" / me["id"]).glob(f"{asset['asset_id']}.*"))


# ── Image-source safety ──────────────────────────────────────────────────
@pytest.mark.parametrize("source", [
    "http://127.0.0.1:8000/api/v1/health",
    "http://localhost/secret.png",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/image.png",
    "http://[::1]/image.png",
])
def test_private_network_urls_are_refused(authed_client, source):
    res = authed_client.post("/api/v1/query", json={"query": "Describe this scene.",
                                                    "images": [{"id": "i", "modality": "optical", "url_or_base64": source}]})
    assert res.status_code == 400 and res.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
    assert "private" in res.json()["error"]["message"] or "local" in res.json()["error"]["message"]


def test_local_file_paths_are_refused(authed_client):
    secret = DATA_DIR / ".secret_key"
    secret.write_text("x")
    for source in (str(secret), str(DATA_DIR / "satquery.db"), "C:/Windows/win.ini"):
        res = authed_client.post("/api/v1/query", json={"query": "Describe this scene.",
                                                        "images": [{"id": "i", "modality": "optical", "url_or_base64": source}]})
        assert res.status_code == 400, source


# ── Asset previews (API v2.1.0) ──────────────────────────────────────────
def test_asset_preview_is_png_for_owner_only(two_users):
    import rasterio
    from rasterio.transform import from_bounds
    import numpy as np

    a, b = two_users
    buf = io.BytesIO()
    with rasterio.open(buf, "w", driver="GTiff", height=1500, width=2000, count=3, dtype="uint16",
                       crs="EPSG:4326", transform=from_bounds(77, 28, 77.2, 28.2, 2000, 1500)) as dst:
        dst.write(np.random.randint(0, 4000, (3, 1500, 2000), dtype=np.uint16))
    asset = _upload(a, buf.getvalue(), "scene.tif")

    res = a.get(f"/api/v1/assets/{asset['asset_id']}/preview")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert max(Image.open(io.BytesIO(res.content)).size) <= 1024
    assert a.get(f"/api/v1/assets/{asset['asset_id']}/preview").content == res.content  # cached
    assert b.get(f"/api/v1/assets/{asset['asset_id']}/preview").status_code == 404
