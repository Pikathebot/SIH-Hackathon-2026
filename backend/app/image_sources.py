"""
Where query images come from, and the safety rules for each source (API_CONTRACT.md v2.0.0).

- Uploaded assets: looked up in `images` by id *and owner*. Another user's asset is
  indistinguishable from a missing one (404), so ids cannot be probed.
- Remote URLs: only http(s) URLs whose host resolves exclusively to public addresses.
  Redirects are followed by hand (max 3) and each hop is re-checked, so a public URL
  cannot bounce the server into 127.0.0.1, the LAN or a cloud metadata endpoint.
  Residual risk: DNS rebinding between our check and httpx's own lookup. Acceptable
  for local-first use; a cloud deployment should add egress filtering as well.
- Local filesystem paths are never accepted from clients.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DATA_DIR
from app.errors import ApiError
from app.models.db import ImageRecord

ASSET_URL_RE = re.compile(r"^(?:/api/v1/assets/|assets/)?(?P<id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
_MAX_REDIRECTS = 3


class UnsafeUrlError(ValueError):
    pass


# ---------------------------------------------------------------------------
# File type sniffing (magic bytes, never the extension)
# ---------------------------------------------------------------------------
def sniff_image_type(head: bytes) -> Optional[str]:
    """Return 'tiff' | 'jp2' | 'png' | 'jpeg' for supported raster formats, else None."""
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):  # TIFF / BigTIFF
        return "tiff"
    if head[:12] == b"\x00\x00\x00\x0cjP  \r\n\x87\n" or head[:4] == b"\xff\x4f\xff\x51":
        return "jp2"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    return None


EXTENSIONS = {"tiff": ".tif", "jp2": ".jp2", "png": ".png", "jpeg": ".jpg"}


# ---------------------------------------------------------------------------
# Uploaded assets
# ---------------------------------------------------------------------------
def parse_asset_ref(value: Optional[str]) -> Optional[str]:
    """'/api/v1/assets/<uuid>' or a bare '<uuid>' → '<uuid>'; anything else → None."""
    if not value:
        return None
    m = ASSET_URL_RE.match(value.strip())
    return m.group("id") if m else None


async def resolve_owned_asset(db: AsyncSession, user_id: str, asset_id: str) -> tuple[ImageRecord, Path]:
    row = (await db.execute(
        select(ImageRecord).where(ImageRecord.id == asset_id, ImageRecord.user_id == user_id)
    )).scalar_one_or_none()
    path = (DATA_DIR / row.storage_path).resolve() if row else None
    if row is None or path is None or not path.is_file() or DATA_DIR.resolve() not in path.parents:
        raise ApiError(404, "NOT_FOUND", "Image not found.")
    return row, path


# ---------------------------------------------------------------------------
# Remote URLs
# ---------------------------------------------------------------------------
def _assert_public_host(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeUrlError("Only http(s) URLs are supported.")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host '{parts.hostname}'.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeUrlError("URLs pointing at local or private network addresses are not allowed.")


def fetch_public_url(url: str, max_bytes: int, timeout: float = 30.0) -> bytes:
    """Download a URL that resolves only to public addresses, capped at max_bytes."""
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            _assert_public_host(url)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers.get("location", ""))
                    continue
                resp.raise_for_status()
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise UnsafeUrlError(f"Remote image is larger than {max_bytes // (1024 * 1024)} MB.")
                return bytes(buf)
    raise UnsafeUrlError("Too many redirects.")
