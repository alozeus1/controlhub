#!/usr/bin/env python3
"""
Generate the authoritative endpoint inventory from the live Flask URL map.

Hand-maintained route lists rot. This walks ``app.url_map`` for the real routes,
then AST-parses the route modules to recover the decorator stack applied to each
view function, so the auth posture of every endpoint is derived from the code
rather than from a comment.

Usage:
    python scripts/dump_endpoint_inventory.py            # write the markdown artifact
    python scripts/dump_endpoint_inventory.py --check    # exit 1 if an unregistered
                                                         # public route appears

``--check`` is the CI-usable form: it fails when a route is reachable without an
authentication decorator and is not in ``PUBLIC_ALLOWLIST``, which makes "a new
endpoint accidentally shipped unauthenticated" a build failure instead of a
finding in someone's later audit.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Decorators that establish an authenticated principal.
AUTH_DECORATORS = {
    "require_role",
    "require_active_user",
    "require_scope",
    "require_admin",
    "jwt_required",
    "require_elevated_permission",
    "require_permission",
}
# Decorators that add a second factor / recency requirement on top of auth.
STEPUP_DECORATORS = {"require_elevation", "require_elevated_permission", "require_mfa"}
# Decorators that add throttling.
LIMIT_DECORATORS = {"limit"}

# Routes that are intentionally reachable without an authentication *decorator*.
# Every entry needs a reason, and where a route authenticates inside the handler
# instead, the reason names the mechanism — those are not really public, they just
# cannot be recognised from the decorator stack. Adding an entry is a security
# decision and should be reviewed as one.
PUBLIC_ALLOWLIST = {
    # ── Genuinely anonymous ──────────────────────────────────────────────────
    "general.home": "Serves the static landing template. No data.",
    "general.healthz": "Liveness probe used by the container HEALTHCHECK. Returns {'status':'ok'}.",
    "general.readyz": "Readiness probe. Reports dependency reachability only, no detail.",
    "general.get_features": (
        "Boolean module on/off flags the SPA needs before login. Exposes which modules "
        "exist, never their contents."
    ),
    "static": "Flask static asset serving; ships only files under app/static.",
    # ── Pre-authentication steps of the login flow ───────────────────────────
    "auth.login": "Credential exchange. Rate-limited 10/min; MFA evaluation fails closed.",
    "auth.forgot_password": (
        "Reset initiation. Rate-limited 5/min, uniform response so addresses cannot be "
        "enumerated, and the link origin comes from config, not the Host header."
    ),
    "auth.reset_password": (
        "Authenticated by the hashed single-use reset token. Rate-limited 5/min; bumps the "
        "session epoch so pre-reset sessions die."
    ),
    "mfa.mfa_login_verify": (
        "Second factor. Authenticated by a purpose-scoped short-lived challenge token; "
        "rate-limited 10/min with lockout."
    ),
    "sso_public.sso_status": "Reports only whether SSO is enabled plus its display name and login URL.",
    "sso_public.sso_login": "Initiates the IdP redirect. Signed, expiring state parameter.",
    "sso_public.sso_callback": "IdP code-exchange endpoint. Validates the signed state and nonce.",
    # ── Authenticated inside the handler ─────────────────────────────────────
    "feature_flags.sdk_endpoint": (
        "IN-HANDLER AUTH: requires an active, project-bound SDK key (hashed at rest) via "
        "X-SDK-Key. Rate-limited 60/min. Not reachable anonymously."
    ),
    "public_email.ses_webhook": (
        "IN-HANDLER AUTH: SNS signature verified against a host-pinned AWS signing "
        "certificate, bound to SNS_TOPIC_ARN, with a message-age limit. See "
        "tests/test_sns_webhook_trust.py."
    ),
    "public_email.unsubscribe": "IN-HANDLER AUTH: opaque per-subscriber unsubscribe token. RFC 8058 GET target.",
    "public_email.unsubscribe_post": "IN-HANDLER AUTH: opaque per-subscriber unsubscribe token. RFC 8058 POST target.",
}


def collect_decorators() -> dict[str, list[str]]:
    """Map ``<module>.<function>`` -> decorator names, by AST-parsing route modules."""
    found: dict[str, list[str]] = {}
    for path in sorted((REPO_ROOT / "app" / "routes").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names: list[str] = []
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(target, ast.Name):
                    names.append(target.id)
                elif isinstance(target, ast.Attribute):
                    names.append(target.attr)
            found[f"{path.stem}.{node.name}"] = names
    return found


def classify(decorators: list[str]) -> tuple[str, str, str]:
    """Return (auth posture, step-up marker, throttle marker) for a decorator stack."""
    auth = "PUBLIC"
    if any(d in AUTH_DECORATORS for d in decorators):
        if "require_scope" in decorators:
            auth = "service-or-human"
        elif "require_role" in decorators:
            auth = "role-gated"
        else:
            auth = "authenticated"
    stepup = "yes" if any(d in STEPUP_DECORATORS for d in decorators) else "-"
    throttle = "yes" if any(d in LIMIT_DECORATORS for d in decorators) else "-"
    return auth, stepup, throttle


def build_app():
    os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    os.environ.setdefault("FLASK_APP", "wsgi.py")
    os.environ.setdefault("JWT_SECRET_KEY", "inventory-dump-only")
    os.environ.setdefault("SECRET_KEY", "inventory-dump-only")
    from app import create_app

    return create_app()


def gather():
    app = build_app()
    decorators = collect_decorators()
    rows = []
    for rule in app.url_map.iter_rules():
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        endpoint = rule.endpoint
        func_key = None
        if "." in endpoint:
            _bp, _, func = endpoint.rpartition(".")
            # The blueprint name need not match the module name, so match on the
            # view function name and fall back to a unique-suffix lookup.
            candidates = [k for k in decorators if k.endswith(f".{func}")]
            func_key = candidates[0] if len(candidates) == 1 else None
            if func_key is None and candidates:
                func_key = candidates[0]
        decs = decorators.get(func_key, []) if func_key else []
        auth, stepup, throttle = classify(decs)
        rows.append(
            {
                "methods": ",".join(methods) or "-",
                "rule": str(rule),
                "endpoint": endpoint,
                "auth": auth,
                "stepup": stepup,
                "throttle": throttle,
                "decorators": [d for d in decs if d not in {"route", "get", "post", "put", "patch", "delete"}],
            }
        )
    rows.sort(key=lambda r: (r["rule"], r["methods"]))
    return rows


def unregistered_public(rows) -> list[dict]:
    return [r for r in rows if r["auth"] == "PUBLIC" and r["endpoint"] not in PUBLIC_ALLOWLIST]


def render(rows) -> str:
    total = len(rows)
    by_auth: dict[str, int] = defaultdict(int)
    for r in rows:
        by_auth[r["auth"]] += 1
    stepup = [r for r in rows if r["stepup"] == "yes"]
    throttled = [r for r in rows if r["throttle"] == "yes"]

    out: list[str] = []
    out.append("# ControlHub — Endpoint Inventory")
    out.append("")
    out.append(
        "> Generated by `scripts/dump_endpoint_inventory.py` from the live Flask URL map. "
        "Do not edit by hand — regenerate."
    )
    out.append("")
    out.append("## Totals")
    out.append("")
    out.append("| Metric | Count |")
    out.append("| --- | --- |")
    out.append(f"| Routes (excluding HEAD/OPTIONS) | {total} |")
    for k in sorted(by_auth):
        out.append(f"| Posture: {k} | {by_auth[k]} |")
    out.append(f"| Requires step-up / elevation | {len(stepup)} |")
    out.append(f"| Carries an explicit rate limit | {len(throttled)} |")
    out.append("")

    unreg = unregistered_public(rows)
    out.append("## Unregistered public routes")
    out.append("")
    if unreg:
        out.append("**FAIL — these are reachable without an authenticated principal and are not allowlisted:**")
        out.append("")
        out.append("| Methods | Rule | Endpoint |")
        out.append("| --- | --- | --- |")
        for r in unreg:
            out.append(f"| {r['methods']} | `{r['rule']}` | `{r['endpoint']}` |")
    else:
        out.append("None. Every public route is declared in `PUBLIC_ALLOWLIST` with a reason.")
    out.append("")

    out.append("## Declared public surface")
    out.append("")
    out.append("| Endpoint | Reason |")
    out.append("| --- | --- |")
    for ep in sorted(PUBLIC_ALLOWLIST):
        present = any(r["endpoint"] == ep for r in rows)
        marker = "" if present else " _(not currently routed)_"
        out.append(f"| `{ep}` | {PUBLIC_ALLOWLIST[ep]}{marker} |")
    out.append("")

    out.append("## Full route table")
    out.append("")
    out.append("| Methods | Rule | Endpoint | Posture | Step-up | Limit | Decorators |")
    out.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        decs = ", ".join(f"`{d}`" for d in r["decorators"]) or "-"
        out.append(
            f"| {r['methods']} | `{r['rule']}` | `{r['endpoint']}` | {r['auth']} | "
            f"{r['stepup']} | {r['throttle']} | {decs} |"
        )
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit non-zero on an unregistered public route")
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "security" / "endpoint-inventory.md"),
        help="output path for the markdown artifact",
    )
    args = parser.parse_args()

    rows = gather()
    unreg = unregistered_public(rows)

    if args.check:
        if unreg:
            print("FAIL: routes reachable without authentication and not allowlisted:")
            for r in unreg:
                print(f"  {r['methods']:12} {r['rule']:50} {r['endpoint']}")
            print("\nAdd an auth decorator, or add the endpoint to PUBLIC_ALLOWLIST with a reason.")
            return 1
        print(f"OK: {len(rows)} routes; every public route is allowlisted.")
        return 0

    Path(args.out).write_text(render(rows), encoding="utf-8")
    print(f"wrote {args.out} ({len(rows)} routes, {len(unreg)} unregistered public)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
