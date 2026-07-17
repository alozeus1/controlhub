"""
P1-4 regression: centralized JSON error handling.
Every error returns {error, code, request_id} JSON — never HTML, never internals.
"""


def _assert_json_error(resp, status, code):
    assert resp.status_code == status
    assert resp.content_type.startswith("application/json")
    body = resp.get_json()
    assert body["code"] == code
    assert "error" in body
    assert "request_id" in body


def test_404_returns_json(client):
    _assert_json_error(client.get("/admin/this-route-does-not-exist"), 404, "NOT_FOUND")


def test_405_returns_json(client):
    # /features is GET-only
    _assert_json_error(client.post("/features"), 405, "METHOD_NOT_ALLOWED")


def test_uncaught_exception_returns_safe_500(app, client):
    # Register a throwaway route that raises; disable propagation so the handler runs.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.route("/_boom_test")
    def _boom():
        raise ValueError("secret internal detail: db password xyz")

    resp = client.get("/_boom_test")
    _assert_json_error(resp, 500, "INTERNAL_ERROR")
    body = resp.get_json()
    # Must NOT leak the exception text.
    assert "secret internal detail" not in body["error"]
    assert "xyz" not in str(body)


def test_response_has_request_id_header(client):
    r = client.get("/features")
    assert r.headers.get("X-Request-ID")
