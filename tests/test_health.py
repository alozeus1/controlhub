def test_healthz_returns_200(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_healthz_returns_request_id_header(client):
    response = client.get("/healthz")
    assert "X-Request-ID" in response.headers


def test_healthz_preserves_incoming_request_id(client):
    response = client.get("/healthz", headers={"X-Request-ID": "test-123"})
    assert response.headers["X-Request-ID"] == "test-123"
