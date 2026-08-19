"""
Every route reachable without an authentication decorator must be a reviewed decision.

ControlHub has 280 routes across 33 blueprints. The realistic failure mode is not a
deliberately public endpoint — it is a new `@blueprint.get(...)` that ships without
`@require_role` because the author forgot, and nobody notices until an audit. This
test turns that into a build failure: a route with no authentication decorator must
appear in `PUBLIC_ALLOWLIST` in scripts/dump_endpoint_inventory.py, with a reason.

Adding an entry there is a security decision and shows up in review as one.
"""
import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "dump_endpoint_inventory.py"


def _load_inventory_module():
    spec = importlib.util.spec_from_file_location("dump_endpoint_inventory", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def inventory():
    return _load_inventory_module()


def test_no_route_is_reachable_without_a_reviewed_decision(inventory):
    rows = inventory.gather()
    offenders = inventory.unregistered_public(rows)
    assert not offenders, (
        "These routes have no authentication decorator and are not in PUBLIC_ALLOWLIST:\n"
        + "\n".join(f"  {r['methods']:12} {r['rule']:52} {r['endpoint']}" for r in offenders)
        + "\n\nAdd an auth decorator, or add the endpoint to PUBLIC_ALLOWLIST with a reason."
    )


def test_the_gate_actually_fires_on_an_unregistered_public_route(inventory):
    """A guard that cannot fail proves nothing — verify it flags a synthetic route."""
    synthetic = [
        {"auth": "PUBLIC", "endpoint": "newmodule.leaky_export", "methods": "GET",
         "rule": "/admin/newmodule/export", "stepup": "-", "throttle": "-", "decorators": []},
        {"auth": "role-gated", "endpoint": "newmodule.safe", "methods": "GET",
         "rule": "/admin/newmodule/ok", "stepup": "-", "throttle": "-", "decorators": ["require_role"]},
    ]
    flagged = inventory.unregistered_public(synthetic)
    assert [r["endpoint"] for r in flagged] == ["newmodule.leaky_export"]


def test_allowlist_has_no_stale_entries(inventory):
    """An allowlisted endpoint that no longer exists should be removed, not left behind."""
    routed = {r["endpoint"] for r in inventory.gather()}
    stale = sorted(ep for ep in inventory.PUBLIC_ALLOWLIST if ep not in routed)
    assert not stale, f"PUBLIC_ALLOWLIST names endpoints that are not routed: {stale}"


def test_every_allowlist_entry_states_a_reason(inventory):
    thin = sorted(ep for ep, reason in inventory.PUBLIC_ALLOWLIST.items() if len(reason.strip()) < 25)
    assert not thin, f"These allowlist entries need a real justification: {thin}"


def test_privileged_modules_are_never_classified_public(inventory):
    """
    Defence in depth against a bad allowlist edit: the modules that hold restricted
    data must not contain a public route under any circumstances.
    """
    restricted_prefixes = (
        "/admin/secrets",
        "/admin/env-configs",
        "/admin/roles",
        "/admin/users",
        "/admin/people",
        "/admin/elevation",
        "/admin/service-accounts",
        "/admin/audit",
        "/admin/org-settings",
    )
    leaks = [
        r for r in inventory.gather()
        if r["auth"] == "PUBLIC" and r["rule"].startswith(restricted_prefixes)
    ]
    assert not leaks, (
        "Restricted-data routes must never be public:\n"
        + "\n".join(f"  {r['methods']:12} {r['rule']:52} {r['endpoint']}" for r in leaks)
    )
