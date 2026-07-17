"""
SSRF-hardened outbound HTTP for server-initiated fetches (audit finding A-6).

Used for OIDC discovery/JWKS/token/userinfo requests, where the destination URL
is influenced by admin configuration (and, via the discovery document, by the
identity provider). Without a guard an attacker who controls that configuration
could point requests at internal services or the cloud instance-metadata
endpoint (169.254.169.254) and exfiltrate credentials.

Protections:
  - scheme allowlist (http/https); HTTPS required when not explicitly relaxed
    for local development;
  - DNS resolution of the target host, with EVERY resolved address checked
    against loopback / private / link-local / multicast / reserved /
    unspecified ranges for both IPv4 and IPv6 (this covers 169.254.169.254 and
    the IPv6 metadata address);
  - redirects are followed manually, re-validating each hop (defends against
    redirect-based SSRF);
  - strict connect/read timeouts and a response-size cap;
  - optional content-type enforcement.

Residual risk: a TOCTOU DNS-rebinding window remains between validation and the
socket connect. It is low for these admin-gated flows and is tracked as a
hardening backlog item (pin the validated IP with TLS SNI). Set
SSO_ALLOW_PRIVATE_NETWORKS=true ONLY for local development against a private
IdP; it must be false in staging/production.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests
from flask import current_app

DEFAULT_TIMEOUT = (5, 8)          # (connect, read) seconds
MAX_RESPONSE_BYTES = 5 * 1024 * 1024   # 5 MiB
MAX_REDIRECTS = 3


class SsrfError(ValueError):
    """Raised when a URL is rejected by the SSRF guard."""


def _allow_private() -> bool:
    val = current_app.config.get("SSO_ALLOW_PRIVATE_NETWORKS")
    if val is None:
        import os
        val = os.environ.get("SSO_ALLOW_PRIVATE_NETWORKS", "")
    return str(val).lower() in ("1", "true", "yes", "on")


def _is_production() -> bool:
    env = (current_app.config.get("ENV")
           or current_app.config.get("FLASK_ENV") or "").lower()
    if env in ("production", "prod", "staging"):
        return True
    import os
    return os.environ.get("FLASK_ENV", "").lower() in ("production", "prod", "staging")


def _ip_is_blocked(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local        # 169.254.0.0/16 and fe80::/10 (metadata)
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Validate a URL is safe to fetch, or raise SsrfError."""
    if not url or not isinstance(url, str):
        raise SsrfError("Empty or invalid URL")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise SsrfError(f"Blocked URL scheme: {scheme or '(none)'}")

    allow_private = _allow_private()
    if scheme != "https" and not allow_private:
        raise SsrfError("HTTPS is required for outbound identity-provider requests")

    host = parsed.hostname
    if not host:
        raise SsrfError("URL has no host")

    # Resolve ALL addresses; reject if any is a blocked/internal range.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SsrfError(f"Could not resolve host: {host}") from exc

    resolved = {info[4][0] for info in infos}
    if not resolved:
        raise SsrfError(f"Host did not resolve: {host}")

    if allow_private:
        return
    for ip_str in resolved:
        if _ip_is_blocked(ip_str):
            raise SsrfError("URL resolves to a non-public (internal) address")


def safe_request(method, url, *, expect_json=False, timeout=DEFAULT_TIMEOUT, **kwargs):
    """
    Perform an SSRF-validated HTTP request, following redirects manually and
    re-validating each hop. Enforces timeout and a response-size cap.
    """
    kwargs.pop("allow_redirects", None)  # we handle redirects ourselves
    current_url = url
    for _hop in range(MAX_REDIRECTS + 1):
        assert_public_url(current_url)
        resp = requests.request(
            method, current_url,
            timeout=timeout, allow_redirects=False, stream=True, **kwargs,
        )
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise SsrfError("Redirect without Location header")
            # Resolve relative redirects against the current URL.
            from urllib.parse import urljoin
            current_url = urljoin(current_url, location)
            continue

        # Enforce a hard size cap.
        content = resp.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
        if len(content) > MAX_RESPONSE_BYTES:
            resp.close()
            raise SsrfError("Response exceeded maximum allowed size")
        resp._content = content  # noqa: SLF001 — cache for .json()/.text
        resp.close()

        if expect_json:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "json" not in ctype:
                raise SsrfError(f"Expected JSON response, got content-type: {ctype or '(none)'}")
        return resp

    raise SsrfError("Too many redirects")


def safe_get(url, **kwargs):
    return safe_request("GET", url, **kwargs)


def safe_post(url, **kwargs):
    return safe_request("POST", url, **kwargs)
