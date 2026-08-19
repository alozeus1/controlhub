"""
SSO via OpenID Connect (feature 4).

Admin config screen + the OIDC authorization-code login flow with claim->role
mapping. Works with Okta, Azure AD, Google Workspace, Auth0, etc.

Needs a live IdP (client id/secret + discovery URL) to exercise end to end.

Security: the id_token signature is verified against the provider JWKS, with
audience, issuer, expiry, and nonce all checked (see _verify_id_token); the
userinfo endpoint is only a secondary source for the group/role claim. The CSRF
state and nonce are carried in a signed, short-lived JWT.
"""
import os
import secrets as pysecrets
from urllib.parse import urlencode

from flask import Blueprint, request, jsonify, redirect, current_app
from flask_jwt_extended import decode_token

from app.extensions import db
from app.models import User, SsoConfig
from app.permissions import require_elevated_permission
from app.services.secret_crypto import encrypt_secret, decrypt_secret
from app.services.safe_http import safe_get, safe_post, assert_public_url
from app.utils.audit import log_action
from flask_jwt_extended import create_access_token as _cat
from datetime import timedelta

sso_bp = Blueprint("sso", __name__)          # admin config, under /admin
sso_public_bp = Blueprint("sso_public", __name__)  # login flow, unauthenticated


def _base_url():
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:9000").rstrip("/")


def _ui_base_url():
    return os.environ.get("UI_BASE_URL", "http://localhost:3001").rstrip("/")


def _discovery(cfg):
    # SSRF-guarded: rejects internal/metadata addresses and non-HTTPS in prod.
    r = safe_get(cfg.discovery_url, expect_json=True)
    r.raise_for_status()
    return r.json()


# ─── Admin configuration ──────────────────────────────────────────────────────

@sso_bp.get("/sso/config")
@require_elevated_permission("manage_sso")
def get_sso_config():
    return jsonify(SsoConfig.get().to_dict())


@sso_bp.put("/sso/config")
@require_elevated_permission("manage_sso")
def update_sso_config():
    data = request.get_json() or {}
    cfg = SsoConfig.get()
    for f in ("display_name", "discovery_url", "client_id", "default_role", "role_claim"):
        if f in data:
            setattr(cfg, f, data[f])
    if "enabled" in data:
        cfg.enabled = bool(data["enabled"])
    if data.get("client_secret"):
        cfg.client_secret_enc = encrypt_secret(data["client_secret"], purpose="sso_client_secret")
    if "claim_role_map" in data and isinstance(data["claim_role_map"], dict):
        cfg.claim_role_map = data["claim_role_map"]
    if "allowed_domains" in data:
        doms = data["allowed_domains"] or []
        if isinstance(doms, str):
            doms = [d.strip() for d in doms.split(",")]
        cfg.allowed_domains = [d.lower().lstrip("@").strip() for d in doms if str(d).strip()]
    db.session.commit()
    log_action("sso.config.updated", actor=getattr(request, "current_user", None),
               target_type="sso_config", target_id=1, details={"enabled": cfg.enabled})
    return jsonify(cfg.to_dict())


@sso_bp.post("/sso/test")
@require_elevated_permission("manage_sso")
def test_sso_discovery():
    """Validate that the discovery URL resolves and exposes required endpoints."""
    cfg = SsoConfig.get()
    if not cfg.discovery_url:
        return jsonify({"ok": False, "error": "No discovery URL configured"}), 400
    try:
        doc = _discovery(cfg)
        missing = [k for k in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint")
                   if k not in doc]
        if missing:
            return jsonify({"ok": False, "error": f"Discovery doc missing: {', '.join(missing)}"}), 400
        return jsonify({"ok": True, "issuer": doc.get("issuer"),
                        "authorization_endpoint": doc.get("authorization_endpoint")})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


# ─── Public login flow ────────────────────────────────────────────────────────

@sso_public_bp.get("/sso/status")
def sso_status():
    cfg = SsoConfig.get()
    return jsonify({
        "enabled": cfg.enabled and bool(cfg.discovery_url and cfg.client_id),
        "display_name": cfg.display_name or "Single Sign-On",
        "login_url": f"{_base_url()}/auth/sso/login",
    })


@sso_public_bp.get("/sso/login")
def sso_login():
    cfg = SsoConfig.get()
    if not (cfg.enabled and cfg.discovery_url and cfg.client_id):
        return jsonify({"error": "SSO is not configured"}), 400
    try:
        doc = _discovery(cfg)
    except Exception as exc:
        return jsonify({"error": f"Could not reach identity provider: {exc}"}), 502

    nonce = pysecrets.token_urlsafe(16)
    # Sign the state so the callback can trust it without server-side storage.
    state = _cat(identity="sso", additional_claims={"purpose": "sso_state", "nonce": nonce},
                 expires_delta=timedelta(minutes=10))
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": f"{_base_url()}/auth/sso/callback",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    return redirect(f"{doc['authorization_endpoint']}?{urlencode(params)}")


@sso_public_bp.get("/sso/callback")
def sso_callback():
    cfg = SsoConfig.get()
    code = request.args.get("code")
    state = request.args.get("state", "")
    if not code:
        return _fail_redirect("missing_code")
    try:
        decoded = decode_token(state)
        if decoded.get("purpose") != "sso_state":
            return _fail_redirect("bad_state")
    except Exception:
        return _fail_redirect("bad_state")

    try:
        doc = _discovery(cfg)
        secret = decrypt_secret(cfg.client_secret_enc, purpose="sso_client_secret") if cfg.client_secret_enc else ""
        token_res = safe_post(doc["token_endpoint"], expect_json=True, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{_base_url()}/auth/sso/callback",
            "client_id": cfg.client_id,
            "client_secret": secret,
        })
        token_res.raise_for_status()
        tok = token_res.json()
        access = tok.get("access_token")
        id_token = tok.get("id_token")
    except Exception as exc:
        current_app.logger.warning("SSO callback token exchange failed: %s", exc)
        return _fail_redirect("provider_error")

    # Verify the id_token signature against the provider JWKS (authoritative
    # identity). aud/iss/exp and nonce are all checked.
    claims = {}
    if id_token:
        try:
            claims = _verify_id_token(cfg, doc, id_token, decoded.get("nonce"))
        except Exception as exc:
            current_app.logger.warning("SSO id_token verification failed: %s", exc)
            return _fail_redirect("token_verification_failed")

    # userinfo is a secondary source (e.g. for the group/role claim).
    userinfo = {}
    if access:
        try:
            userinfo = safe_get(doc["userinfo_endpoint"], expect_json=True,
                                headers={"Authorization": f"Bearer {access}"}).json()
        except Exception:
            userinfo = {}

    identity = {**userinfo, **claims}   # verified id_token claims take precedence
    email = (claims.get("email") or userinfo.get("email") or "").strip().lower()
    if not email:
        return _fail_redirect("no_email")
    # If the id_token asserts email_verified is false, reject.
    if claims and claims.get("email_verified") is False:
        return _fail_redirect("email_unverified")

    # Domain allowlist.
    domains = cfg.allowed_domains or []
    if domains and email.split("@")[-1] not in domains:
        return _fail_redirect("domain_not_allowed")

    role = _map_role(cfg, identity)
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, role=role, is_active=True)
        user.set_password(pysecrets.token_urlsafe(24))  # unusable local password
        db.session.add(user)
        db.session.commit()
        log_action("sso.user_provisioned", actor=user, target_type="user",
                   target_id=user.id, target_label=email, details={"role": role})
    if not user.is_active:
        return _fail_redirect("account_disabled")

    from app.services.session_security import issue_token_pair
    access_token, refresh_token, _ = issue_token_pair(user)
    log_action("sso.login", actor=user, target_type="user", target_id=user.id, target_label=email)
    # Hand tokens to the SPA via URL fragment (not sent to servers/logs).
    frag = urlencode({"access_token": access_token, "refresh_token": refresh_token})
    return redirect(f"{_ui_base_url()}/ui/sso-callback#{frag}")


def _verify_id_token(cfg, doc, id_token, expected_nonce):
    """
    Verify an OIDC id_token: signature (via provider JWKS), audience, issuer,
    expiry, and nonce. Returns the verified claims dict or raises.
    """
    import jwt
    from jwt import PyJWKClient

    jwks_uri = doc.get("jwks_uri")
    if not jwks_uri:
        raise ValueError("Provider discovery has no jwks_uri")
    # PyJWKClient fetches the JWKS itself (bypassing safe_http), so validate the
    # URL against the SSRF guard before letting it connect.
    assert_public_url(jwks_uri)
    signing_key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "RS384", "RS512", "ES256"],
        audience=cfg.client_id,
        issuer=doc.get("issuer"),
        options={"require": ["exp", "iat", "aud", "iss"]},
    )
    if expected_nonce and claims.get("nonce") != expected_nonce:
        raise ValueError("nonce mismatch")
    return claims


def _map_role(cfg, userinfo):
    mapping = cfg.claim_role_map or {}
    claim = cfg.role_claim or "groups"
    values = userinfo.get(claim)
    if isinstance(values, str):
        values = [values]
    for v in (values or []):
        if v in mapping:
            return mapping[v]
    return cfg.default_role or "user"


def _fail_redirect(reason):
    return redirect(f"{_ui_base_url()}/ui/login?sso_error={reason}")
