"""Remote image URLs: only public addresses, connected to by the IP that was checked."""
import socket

import httpx
import pytest

from app import image_sources
from app.image_sources import UnsafeUrlError, fetch_public_url

PUBLIC = "93.184.216.34"


def _fake_dns(monkeypatch, answers):
    """getaddrinfo returning answers[host] (a list of IPs, or a list of lists consumed per call)."""
    calls = {}

    def fake(host, port, *a, **kw):
        ips = answers[host]
        if ips and isinstance(ips[0], list):  # one answer per lookup (DNS rebinding)
            n = calls.get(host, 0)
            calls[host] = n + 1
            ips = ips[min(n, len(ips) - 1)]
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))
                for ip in ips]

    monkeypatch.setattr(image_sources.socket, "getaddrinfo", fake)
    return calls


@pytest.mark.parametrize("ips", [["127.0.0.1"], ["10.0.0.5"], ["169.254.169.254"], ["::1"],
                                 [PUBLIC, "192.168.1.10"]])
def test_private_or_mixed_resolution_is_rejected(monkeypatch, ips):
    _fake_dns(monkeypatch, {"img.example.com": ips})
    seen = []
    transport = httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, content=b"x"))
    with pytest.raises(UnsafeUrlError):
        fetch_public_url("https://img.example.com/a.png", max_bytes=1024, transport=transport)
    assert seen == []  # nothing was ever requested


def test_connects_to_the_validated_ip_with_real_host_and_sni(monkeypatch):
    # First lookup is public, any later lookup would be loopback (DNS rebinding)
    _fake_dns(monkeypatch, {"img.example.com": [[PUBLIC], ["127.0.0.1"]]})
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"PNGDATA")

    data = fetch_public_url("https://img.example.com:8443/a.png?x=1", max_bytes=1024,
                            transport=httpx.MockTransport(handler))
    assert data == b"PNGDATA"
    (req,) = seen
    assert req.url.host == PUBLIC and req.url.port == 8443 and req.url.path == "/a.png"
    assert req.headers["host"] == "img.example.com:8443"
    assert req.extensions["sni_hostname"] == "img.example.com"


def test_redirect_to_private_host_is_rejected(monkeypatch):
    _fake_dns(monkeypatch, {"img.example.com": [PUBLIC], "internal.example.com": ["10.1.2.3"]})
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "http://internal.example.com/secret"})

    with pytest.raises(UnsafeUrlError):
        fetch_public_url("https://img.example.com/a.png", max_bytes=1024, transport=httpx.MockTransport(handler))
    assert len(seen) == 1


def test_size_cap(monkeypatch):
    _fake_dns(monkeypatch, {"img.example.com": [PUBLIC]})
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 5000))
    with pytest.raises(UnsafeUrlError, match="larger than"):
        fetch_public_url("http://img.example.com/a.png", max_bytes=1000, transport=transport)
