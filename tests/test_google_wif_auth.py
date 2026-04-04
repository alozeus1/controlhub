import pytest

from app.integrations import google_auth


def test_get_google_credentials_requires_wif_env(monkeypatch):
    monkeypatch.delenv("GOOGLE_WIF_AUDIENCE", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", raising=False)
    monkeypatch.delenv("GOOGLE_IMPERSONATE_USER", raising=False)
    monkeypatch.delenv("GOOGLE_WIF_CREDENTIALS_PATH", raising=False)

    with pytest.raises(google_auth.GoogleAuthConfigError) as exc:
        google_auth.get_google_credentials()

    assert "GOOGLE_WIF_AUDIENCE" in str(exc.value)


def test_get_google_credentials_constructs_wif_and_dwd(monkeypatch):
    monkeypatch.setenv(
        "GOOGLE_WIF_AUDIENCE",
        "//iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/pool/providers/provider",
    )
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "controlhub-agent@example.iam.gserviceaccount.com")
    monkeypatch.setenv("GOOGLE_IMPERSONATE_USER", "info@example.com")
    monkeypatch.setenv(
        "GOOGLE_SCOPES",
        "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets",
    )
    monkeypatch.delenv("GOOGLE_WIF_CREDENTIALS_PATH", raising=False)

    captured = {}

    class FakeAwsCredentials:
        def __init__(self, **kwargs):
            captured["aws_kwargs"] = kwargs

    class FakeDelegatedCredentials:
        def __init__(self, **kwargs):
            captured["delegated_kwargs"] = kwargs

    monkeypatch.setattr(google_auth.google_auth_aws, "Credentials", FakeAwsCredentials)
    monkeypatch.setattr(
        google_auth.impersonated_credentials,
        "Credentials",
        FakeDelegatedCredentials,
    )

    creds = google_auth.get_google_credentials()

    assert isinstance(creds, FakeDelegatedCredentials)
    assert captured["aws_kwargs"]["audience"].startswith("//iam.googleapis.com/projects/")
    assert (
        captured["aws_kwargs"]["subject_token_type"]
        == "urn:ietf:params:aws:token-type:aws4_request"
    )
    assert captured["delegated_kwargs"]["target_principal"] == "controlhub-agent@example.iam.gserviceaccount.com"
    assert captured["delegated_kwargs"]["subject"] == "info@example.com"
    assert captured["delegated_kwargs"]["target_scopes"] == [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets",
    ]


def test_get_google_credentials_rejects_invalid_audience(monkeypatch):
    monkeypatch.setenv("GOOGLE_WIF_AUDIENCE", "not-an-audience")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "controlhub-agent@example.iam.gserviceaccount.com")
    monkeypatch.setenv("GOOGLE_IMPERSONATE_USER", "info@example.com")
    monkeypatch.delenv("GOOGLE_WIF_CREDENTIALS_PATH", raising=False)

    with pytest.raises(google_auth.GoogleAuthConfigError) as exc:
        google_auth.get_google_credentials()

    assert "expected" in str(exc.value).lower()
    assert "workloadidentitypools" in str(exc.value).lower()
