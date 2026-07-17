"""A-6: SSRF guard for OIDC outbound requests."""
import pytest

from app.services.safe_http import assert_public_url, SsrfError


def _patch_resolves(monkeypatch, ip):
    import socket

    def fake_getaddrinfo(host, port, *a, **k):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


BLOCKED = [
    ("https://metadata.internal/", "169.254.169.254"),   # cloud metadata (link-local)
    ("https://internal.svc/", "127.0.0.1"),               # loopback
    ("https://internal.svc/", "10.1.2.3"),                # RFC1918
    ("https://internal.svc/", "192.168.0.5"),             # RFC1918
    ("https://internal.svc/", "172.16.9.9"),              # RFC1918
    ("https://internal.svc/", "::1"),                     # IPv6 loopback
    ("https://internal.svc/", "fd00::1"),                 # IPv6 ULA (private)
    ("https://internal.svc/", "fe80::1"),                 # IPv6 link-local
]


@pytest.mark.parametrize("url,ip", BLOCKED)
def test_blocks_internal_addresses(app, monkeypatch, url, ip):
    _patch_resolves(monkeypatch, ip)
    with app.app_context():
        with pytest.raises(SsrfError):
            assert_public_url(url)


def test_blocks_non_https_by_default(app, monkeypatch):
    _patch_resolves(monkeypatch, "93.184.216.34")  # public
    with app.app_context():
        with pytest.raises(SsrfError):
            assert_public_url("http://example.com/.well-known/openid-configuration")


def test_blocks_non_http_scheme(app):
    with app.app_context():
        with pytest.raises(SsrfError):
            assert_public_url("file:///etc/passwd")
        with pytest.raises(SsrfError):
            assert_public_url("gopher://x/")


def test_allows_public_https(app, monkeypatch):
    _patch_resolves(monkeypatch, "93.184.216.34")  # public IP
    with app.app_context():
        assert_public_url("https://accounts.example.com/.well-known/openid-configuration")


def test_dev_escape_hatch_allows_private(app, monkeypatch):
    _patch_resolves(monkeypatch, "127.0.0.1")
    app.config["SSO_ALLOW_PRIVATE_NETWORKS"] = True
    with app.app_context():
        # Explicit local-dev opt-in permits http + loopback (documented, prod=false)
        assert_public_url("http://localhost:8080/.well-known/openid-configuration")
