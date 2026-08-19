"""
Security headers must come from the application, not from a proxy.

nginx.conf carries a full header policy, but nginx only exists in the
docker-compose topology. The Procfile — what Railway runs — starts gunicorn
directly, so a policy that lives only in nginx.conf is absent in production. These
tests assert the application emits it itself, and that a fronting proxy's stricter
value is still respected.
"""
import pytest

from app.utils.security_headers import DEFAULT_CSP


PROBE_PATHS = ["/healthz", "/features", "/auth/login"]


@pytest.mark.parametrize("path", PROBE_PATHS)
def test_csp_is_present_without_a_proxy(client, path):
    resp = client.get(path) if path != "/auth/login" else client.post(path, json={})
    assert resp.headers.get("Content-Security-Policy") == DEFAULT_CSP


@pytest.mark.parametrize("path", PROBE_PATHS)
def test_baseline_headers_are_present(client, path):
    resp = client.get(path) if path != "/auth/login" else client.post(path, json={})
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["Permissions-Policy"] == "geolocation=(), camera=()"
    assert resp.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert resp.headers["X-Permitted-Cross-Domain-Policies"] == "none"


def test_csp_forbids_inline_script_and_framing():
    """The two clauses that matter most for an admin console."""
    assert "script-src 'self'" in DEFAULT_CSP
    assert "unsafe-inline" not in DEFAULT_CSP.split("style-src")[0]
    assert "frame-ancestors 'none'" in DEFAULT_CSP
    assert "object-src 'none'" in DEFAULT_CSP


def test_hsts_is_set_over_tls(client):
    resp = client.get("/healthz", base_url="https://controlhub.example.test")
    assert resp.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"


def test_hsts_is_not_set_over_plain_http(client):
    """A year-long pin asserted from a plaintext dev server is a footgun."""
    resp = client.get("/healthz", base_url="http://localhost")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_always_override(client, monkeypatch):
    monkeypatch.setenv("HSTS_ALWAYS", "true")
    resp = client.get("/healthz", base_url="http://localhost")
    assert resp.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"


def test_csp_is_configurable_without_a_redeploy(client, monkeypatch):
    monkeypatch.setenv("CONTENT_SECURITY_POLICY", "default-src 'none'")
    resp = client.get("/healthz")
    assert resp.headers["Content-Security-Policy"] == "default-src 'none'"


def test_a_proxy_policy_is_not_overwritten(app, client):
    """If nginx already set a policy, the application must not replace it."""
    @app.after_request
    def _pretend_to_be_nginx(response):
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response

    resp = client.get("/healthz")
    # Exactly one policy, and it is the proxy's.
    assert resp.headers.getlist("Content-Security-Policy") == ["default-src 'none'"]


@pytest.mark.parametrize("path", ["/auth/login", "/admin/audit-logs", "/features"])
def test_authenticated_and_api_surfaces_are_no_store(client, path):
    resp = client.get(path) if path != "/auth/login" else client.post(path, json={})
    assert resp.headers.get("Cache-Control") == "no-store"


def test_static_assets_are_still_cacheable(client):
    """no-store must not be applied to hashed static bundles."""
    resp = client.get("/")
    assert resp.headers.get("Cache-Control") != "no-store"
