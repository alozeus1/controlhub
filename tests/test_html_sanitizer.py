"""
P2-6 regression: campaign HTML sanitization strips active content, and campaign
create/update persist only sanitized HTML.
"""
import pytest

from app.services.html_sanitizer import sanitize_email_html


@pytest.mark.parametrize("payload,forbidden", [
    ('<script>alert(1)</script><p>hi</p>', "<script"),
    ('<img src=x onerror="alert(1)">', "onerror"),
    ('<a href="javascript:alert(1)">x</a>', "javascript:"),
    ('<iframe src="https://evil.example"></iframe>', "<iframe"),
    ('<svg/onload=alert(1)>', "onload"),
    ('<div onclick="steal()">x</div>', "onclick"),
    ('<object data="x.swf"></object>', "<object"),
    ('<style>body{background:url(javascript:alert(1))}</style>', "javascript:"),
    ('<p style="background:url(javascript:alert(1))">x</p>', "javascript:"),
])
def test_dangerous_content_stripped(payload, forbidden):
    out = sanitize_email_html(payload)
    assert forbidden.lower() not in out.lower()


def test_safe_email_html_preserved():
    src = ('<div style="color:#333"><h1>Hi {{name}}</h1>'
           '<p>Read <a href="https://webforx.tech">this</a></p>'
           '<img src="https://cdn.example/x.png" alt="x" width="100"></div>')
    out = sanitize_email_html(src)
    assert "<h1>" in out
    assert 'href="https://webforx.tech"' in out
    assert "<img" in out and "https://cdn.example/x.png" in out
    assert "color" in out  # inline style preserved


class _Env:
    pass


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("FEATURE_EMAIL_CAMPAIGNS", "true")


def test_created_campaign_html_is_sanitized(client, email_env, create_user, auth_header):
    admin = create_user("a@x.com", role="admin")
    r = client.post("/admin/email/campaigns", headers=auth_header(admin), json={
        "name": "Evil", "subject": "S",
        "html": '<script>alert(1)</script><p onclick="x()">Hello</p>',
    })
    assert r.status_code == 201
    cid = r.get_json()["id"]
    got = client.get(f"/admin/email/campaigns/{cid}", headers=auth_header(admin)).get_json()
    assert "<script" not in got["html"].lower()
    assert "onclick" not in got["html"].lower()
    assert "Hello" in got["html"]
