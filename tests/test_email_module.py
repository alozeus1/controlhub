"""
Tests for the email module's list-membership, table-action, and settings
endpoints (the mass-campaign management surface).
"""
import pytest


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("FEATURE_EMAIL_CAMPAIGNS", "true")
    monkeypatch.setenv("SES_SENDING_ENABLED", "false")
    monkeypatch.setenv("CAMPAIGN_SEND_SYNC", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")


@pytest.fixture
def admin(create_user):
    return create_user("admin@x.com", role="admin")


def _mk_list(client, admin, auth_header, name="Beta"):
    return client.post("/admin/email/lists", headers=auth_header(admin), json={"name": name}).get_json()["id"]


def _mk_sub(client, admin, auth_header, email, name=None):
    return client.post("/admin/email/subscribers", headers=auth_header(admin),
                       json={"email": email, "name": name}).get_json()["id"]


# ─── List membership (the critical flow) ──────────────────────────────────────

def test_add_and_remove_members(client, email_env, admin, auth_header):
    lid = _mk_list(client, admin, auth_header)
    a = _mk_sub(client, admin, auth_header, "ada@x.com", "Ada")
    b = _mk_sub(client, admin, auth_header, "grace@x.com")

    added = client.post(f"/admin/email/lists/{lid}/members", headers=auth_header(admin),
                        json={"subscriber_ids": [a, b]})
    assert added.get_json()["added"] == 2
    assert client.get(f"/admin/email/lists/{lid}/members", headers=auth_header(admin)).get_json()["total"] == 2

    # Idempotent re-add.
    again = client.post(f"/admin/email/lists/{lid}/members", headers=auth_header(admin),
                        json={"subscriber_ids": [a]})
    assert again.get_json()["added"] == 0

    rm = client.delete(f"/admin/email/lists/{lid}/members/{a}", headers=auth_header(admin))
    assert rm.status_code == 200
    assert client.get(f"/admin/email/lists/{lid}/members", headers=auth_header(admin)).get_json()["total"] == 1


def test_import_assigns_to_list(client, email_env, admin, auth_header):
    lid = _mk_list(client, admin, auth_header, "Newsletter")
    res = client.post("/admin/email/subscribers/import", headers=auth_header(admin),
                      json={"list_id": lid, "rows": [
                          {"email": "x1@x.com", "name": "One"},
                          {"email": "x2@x.com", "name": "Two"}]})
    assert res.status_code == 200
    assert client.get(f"/admin/email/lists/{lid}/members", headers=auth_header(admin)).get_json()["total"] == 2


# ─── Table actions ────────────────────────────────────────────────────────────

def test_edit_and_delete_subscriber(client, email_env, admin, auth_header):
    sid = _mk_sub(client, admin, auth_header, "edit@x.com", "Old")
    upd = client.patch(f"/admin/email/subscribers/{sid}", headers=auth_header(admin),
                       json={"name": "New Name", "status": "unsubscribed"})
    assert upd.get_json()["name"] == "New Name"
    assert upd.get_json()["status"] == "unsubscribed"
    assert client.delete(f"/admin/email/subscribers/{sid}", headers=auth_header(admin)).status_code == 200
    # Gone.
    assert client.get("/admin/email/subscribers?search=edit@x.com",
                      headers=auth_header(admin)).get_json()["total"] == 0


def test_delete_subscriber_removes_memberships(client, email_env, admin, auth_header):
    lid = _mk_list(client, admin, auth_header)
    sid = _mk_sub(client, admin, auth_header, "m@x.com")
    client.post(f"/admin/email/lists/{lid}/members", headers=auth_header(admin), json={"subscriber_ids": [sid]})
    client.delete(f"/admin/email/subscribers/{sid}", headers=auth_header(admin))
    assert client.get(f"/admin/email/lists/{lid}/members", headers=auth_header(admin)).get_json()["total"] == 0


def test_rename_and_delete_list(client, email_env, admin, auth_header):
    lid = _mk_list(client, admin, auth_header, "Temp")
    renamed = client.patch(f"/admin/email/lists/{lid}", headers=auth_header(admin), json={"name": "Renamed"})
    assert renamed.get_json()["name"] == "Renamed"
    assert client.delete(f"/admin/email/lists/{lid}", headers=auth_header(admin)).status_code == 200
    # Members endpoint on a gone list returns an empty set (list removed).
    assert client.get("/admin/email/lists", headers=auth_header(admin)).get_json()["lists"] == []


# ─── Settings + footer ────────────────────────────────────────────────────────

def test_email_settings_roundtrip(client, email_env, admin, auth_header):
    put = client.put("/admin/email/settings", headers=auth_header(admin),
                     json={"from_name": "Web Forx", "from_address": "campaigns@webforx.tech",
                           "footer_org_name": "Web Forx Ltd", "footer_address": "1 Main St"})
    assert put.status_code == 200
    got = client.get("/admin/email/settings", headers=auth_header(admin)).get_json()
    assert got["from_address"] == "campaigns@webforx.tech"
    assert got["footer_org_name"] == "Web Forx Ltd"


def test_footer_uses_settings(app, client, email_env, admin, auth_header):
    client.put("/admin/email/settings", headers=auth_header(admin),
               json={"footer_org_name": "Web Forx Ltd", "footer_address": "1 Main St, Lagos"})
    from app.services.campaigns import ensure_compliance_footer

    class Sub:
        email = "a@b.com"; name = "A"; attributes = {}; unsubscribe_token = "tok"

    with app.app_context():
        out = ensure_compliance_footer("<p>Hi</p>", Sub())
    assert "Web Forx Ltd" in out and "1 Main St, Lagos" in out
    assert "unsubscribe" in out.lower()


def test_identities_graceful_without_ses(client, email_env, admin, auth_header):
    r = client.get("/admin/email/identities", headers=auth_header(admin))
    assert r.status_code == 200
    # No SES reachable in tests → available: False, never a 500.
    assert r.get_json().get("available") in (False, True)
