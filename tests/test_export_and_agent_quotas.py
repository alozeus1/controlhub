"""
Quotas on bulk-extraction and cost-bearing routes.

Two classes of route were previously unthrottled:

* Bulk export — `/admin/audit-logs/export`, `/admin/people/export/csv`,
  `/admin/env-projects/<id>/export`, `/admin/audit-exports/now`. A stolen viewer
  session could pull the whole audit trail, the HR roster and every environment
  configuration in a loop, and each call is a full table scan.
* Cost-bearing — agent request creation and runs, artifact presign and publish.
  These spend AWS and model budget per call, so an unbounded loop is a
  denial-of-wallet primitive, not just load.

The bucket is the authenticated principal, not the source address: per-IP alone
puts every operator behind one office egress into a shared quota while giving a
caller with several source addresses a fresh quota per hop.
"""
import pytest

from app.utils.rate_limit import identity_rate_key


@pytest.fixture
def viewer(create_user):
    return create_user("viewer-quota@webforx.tech", role="viewer")


@pytest.fixture
def other_viewer(create_user):
    return create_user("other-quota@webforx.tech", role="viewer")


@pytest.fixture(autouse=True)
def _reset_limiter(app):
    """Each test starts with empty buckets so ordering cannot couple them."""
    from app.extensions import limiter
    try:
        limiter.reset()
    except Exception:
        pass
    yield
    try:
        limiter.reset()
    except Exception:
        pass


def _exhaust(client, url, headers, limit):
    """Call `url` until the quota is spent; return the first 429 response."""
    statuses = []
    for _ in range(limit + 1):
        resp = client.get(url, headers=headers) if not url.endswith("/now") \
            else client.post(url, headers=headers)
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            return resp, statuses
    return None, statuses


# ── The bucket key itself ────────────────────────────────────────────────────

def test_key_is_the_identity_when_authenticated(app, client, viewer, auth_header):
    with app.test_request_context("/admin/audit-logs/export", headers=auth_header(viewer)):
        key = identity_rate_key()
    assert key == f"user:{viewer.id}"


def test_key_falls_back_to_source_address_when_anonymous(app):
    with app.test_request_context("/admin/audit-logs/export", environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        assert identity_rate_key() == "ip:203.0.113.9"


def test_api_key_bucket_never_contains_the_raw_credential(app):
    """Limiter keys reach Redis keyspace and slow logs; the secret must not."""
    raw = "sk_live_do_not_leak_me"
    with app.test_request_context("/admin/audit-logs/export", headers={"X-API-Key": raw}):
        key = identity_rate_key()
    assert key.startswith("svc:")
    assert raw not in key


def test_distinct_identities_get_distinct_buckets(app, client, viewer, other_viewer, auth_header):
    with app.test_request_context("/x", headers=auth_header(viewer)):
        first = identity_rate_key()
    with app.test_request_context("/x", headers=auth_header(other_viewer)):
        second = identity_rate_key()
    assert first != second


# ── Bulk export is bounded ───────────────────────────────────────────────────

def test_audit_log_export_is_rate_limited(client, viewer, auth_header):
    resp, statuses = _exhaust(client, "/admin/audit-logs/export", auth_header(viewer), 20)
    assert resp is not None, f"no 429 within 21 calls; statuses={statuses}"
    assert resp.status_code == 429


def test_people_csv_export_is_rate_limited(app, client, viewer, auth_header):
    app.config["FEATURE_PEOPLE"] = True
    resp, statuses = _exhaust(client, "/admin/people/export/csv", auth_header(viewer), 20)
    assert resp is not None, f"no 429 within 21 calls; statuses={statuses}"


def test_one_identity_exhausting_its_quota_does_not_block_another(
    client, viewer, other_viewer, auth_header
):
    """
    The property per-IP limiting cannot provide: two operators on the same egress
    address must not share a quota.
    """
    resp, _ = _exhaust(client, "/admin/audit-logs/export", auth_header(viewer), 20)
    assert resp is not None and resp.status_code == 429

    # Same source address, different principal — still served.
    other = client.get("/admin/audit-logs/export", headers=auth_header(other_viewer))
    assert other.status_code != 429, "second identity was blocked by the first identity's quota"


# ── Cost-bearing agent routes are bounded ────────────────────────────────────

def test_agent_run_route_is_rate_limited(app, client, viewer, auth_header):
    """
    Each run spends model and AWS budget. The status code of an individual call
    does not matter here — only that the route stops answering at the quota.
    """
    app.config["FEATURE_AGENT_SERVICE"] = True
    headers = auth_header(viewer)
    saw_429 = False
    for _ in range(21):
        resp = client.post("/admin/agent-requests/1/run", headers=headers)
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "agent run route answered 21 times without a quota"


def test_agent_request_creation_is_rate_limited(app, client, viewer, auth_header):
    app.config["FEATURE_AGENT_SERVICE"] = True
    headers = auth_header(viewer)
    saw_429 = False
    for _ in range(31):
        resp = client.post("/admin/agent-requests", headers=headers, json={})
        if resp.status_code == 429:
            saw_429 = True
            break
    assert saw_429, "agent request creation answered 31 times without a quota"


# ── The limits must not have broken the routes ───────────────────────────────

def test_first_export_call_still_succeeds(client, viewer, auth_header):
    resp = client.get("/admin/audit-logs/export", headers=auth_header(viewer))
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_export_still_requires_authentication(client):
    assert client.get("/admin/audit-logs/export").status_code == 401
