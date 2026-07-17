"""A-5: the legacy server-rendered `ui` blueprint (parallel session auth) is gone."""


def test_no_flask_ui_admin_routes(app):
    # The only /ui/* handling belongs to nginx serving the SPA; Flask must not
    # register the old server-rendered admin routes.
    rules = [str(r) for r in app.url_map.iter_rules()]
    assert not any(r.startswith("/ui/admin") for r in rules), rules
    assert "/ui/login" not in rules


def test_ui_module_exposes_no_blueprint():
    import app.routes.ui as ui_module
    assert not hasattr(ui_module, "ui_bp"), "legacy ui_bp must not exist"


def test_unauthenticated_admin_shell_not_served(client):
    # Previously GET /ui/admin returned a 200 HTML shell with no auth. It must
    # no longer be a live Flask route (404/redirect, never a 200 admin shell).
    resp = client.get("/ui/admin")
    assert resp.status_code != 200
