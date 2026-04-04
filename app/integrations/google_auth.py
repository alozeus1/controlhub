"""Google authentication helpers using AWS->WIF and domain-wide delegation."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import boto3
from google.auth import aws as google_auth_aws
from google.auth import exceptions as google_auth_exceptions
from google.auth import impersonated_credentials


AWS_SUBJECT_TOKEN_TYPE = "urn:ietf:params:aws:token-type:aws4_request"
DEFAULT_GOOGLE_TOKEN_URL = "https://sts.googleapis.com/v1/token"
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
)
AUDIENCE_FORMAT_RE = re.compile(
    r"^//iam\.googleapis\.com/projects/\d+/locations/global/workloadIdentityPools/[^/]+/providers/[^/]+$"
)


class GoogleAuthConfigError(RuntimeError):
    """Raised when keyless Google auth is missing required runtime configuration."""


@dataclass(frozen=True)
class GoogleWIFSettings:
    audience: str
    service_account_email: str
    impersonate_user: str
    scopes: Sequence[str]
    token_url: str
    service_account_impersonation_url: Optional[str]


def _looks_like_placeholder(value: Optional[str]) -> bool:
    if value is None:
        return True
    stripped = str(value).strip()
    if stripped in {"", "...", '""', "''"}:
        return True
    if stripped.startswith("${") and stripped.endswith("}"):
        return True
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    if "__REPLACE" in stripped or "placeholder" in stripped.lower():
        return True
    return False


def _parse_scopes(raw_value: Optional[str]) -> Sequence[str]:
    if _looks_like_placeholder(raw_value):
        return list(DEFAULT_SCOPES)
    normalized = str(raw_value).replace(",", " ")
    scopes = [item.strip() for item in normalized.split(" ") if item.strip()]
    return scopes or list(DEFAULT_SCOPES)


def _load_external_account_template(path_value: Optional[str]) -> dict:
    if _looks_like_placeholder(path_value):
        return {}

    path = Path(str(path_value))
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise GoogleAuthConfigError(
            f"Unable to read GOOGLE_WIF_CREDENTIALS_PATH file '{path}': {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise GoogleAuthConfigError(
            f"GOOGLE_WIF_CREDENTIALS_PATH file '{path}' is not valid JSON: {exc}"
        ) from exc


def _extract_service_account_email(impersonation_url: Optional[str]) -> Optional[str]:
    if not impersonation_url:
        return None
    match = re.search(r"/serviceAccounts/([^:]+):", impersonation_url)
    if not match:
        return None
    return match.group(1)


def _require_value(name: str, value: Optional[str], source_hint: str) -> str:
    if _looks_like_placeholder(value):
        raise GoogleAuthConfigError(
            f"Missing runtime config '{name}'. Set {name} via environment variable "
            f"or a mounted WIF config file ({source_hint})."
        )
    return str(value).strip()


def _validate_audience(audience: str) -> str:
    if not AUDIENCE_FORMAT_RE.match(audience):
        raise GoogleAuthConfigError(
            "Invalid GOOGLE_WIF_AUDIENCE format. Expected:\n"
            "//iam.googleapis.com/projects/<project-number>/locations/global/"
            "workloadIdentityPools/<pool-id>/providers/<provider-id>"
        )
    return audience


def _resolve_wif_settings(
    *,
    subject_email_override: Optional[str] = None,
    scopes_override: Optional[Iterable[str]] = None,
) -> GoogleWIFSettings:
    env = os.environ
    template_data = _load_external_account_template(env.get("GOOGLE_WIF_CREDENTIALS_PATH"))

    audience = env.get("GOOGLE_WIF_AUDIENCE") or template_data.get("audience")
    impersonation_url = (
        env.get("GOOGLE_SERVICE_ACCOUNT_IMPERSONATION_URL")
        or template_data.get("service_account_impersonation_url")
    )
    service_account_email = (
        env.get("GOOGLE_SERVICE_ACCOUNT_EMAIL")
        or template_data.get("service_account_email")
        or _extract_service_account_email(impersonation_url)
    )
    impersonate_user = subject_email_override or env.get("GOOGLE_IMPERSONATE_USER")
    token_url = env.get("GOOGLE_WIF_TOKEN_URL") or template_data.get("token_url") or DEFAULT_GOOGLE_TOKEN_URL

    scopes = list(scopes_override or _parse_scopes(env.get("GOOGLE_SCOPES")))

    return GoogleWIFSettings(
        audience=_validate_audience(
            _require_value(
                "GOOGLE_WIF_AUDIENCE",
                audience,
                "GOOGLE_WIF_CREDENTIALS_PATH",
            )
        ),
        service_account_email=_require_value(
            "GOOGLE_SERVICE_ACCOUNT_EMAIL",
            service_account_email,
            "GOOGLE_WIF_CREDENTIALS_PATH/service_account_impersonation_url",
        ),
        impersonate_user=_require_value(
            "GOOGLE_IMPERSONATE_USER",
            impersonate_user,
            "environment",
        ),
        scopes=scopes,
        token_url=token_url,
        service_account_impersonation_url=impersonation_url,
    )


class _Boto3AwsSecurityCredentialsSupplier(google_auth_aws.AwsSecurityCredentialsSupplier):
    """AWS credential supplier backed by boto3 default credential provider chain."""

    def __init__(self):
        self._session = boto3.Session()

    def get_aws_security_credentials(self, context, request):
        credentials = self._session.get_credentials()
        if not credentials:
            raise google_auth_exceptions.RefreshError(
                "No AWS credentials were found. Configure AWS credentials in environment, "
                "shared config, or task role (App Runner/ECS/EKS)."
            )
        frozen = credentials.get_frozen_credentials()
        if not frozen.access_key or not frozen.secret_key:
            raise google_auth_exceptions.RefreshError(
                "Incomplete AWS credentials. Ensure access key and secret key are available "
                "through the AWS default provider chain."
            )
        return google_auth_aws.AwsSecurityCredentials(
            access_key_id=frozen.access_key,
            secret_access_key=frozen.secret_key,
            session_token=frozen.token,
        )

    def get_aws_region(self, context, request):
        region = (
            self._session.region_name
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        )
        if not region:
            raise google_auth_exceptions.RefreshError(
                "Missing AWS region. Set AWS_REGION (or AWS_DEFAULT_REGION) in runtime config."
            )
        return region


def get_google_credentials(
    subject_email: Optional[str] = None,
    scopes: Optional[Iterable[str]] = None,
):
    """
    Return Google credentials using AWS Workload Identity Federation + DWD.

    Flow:
    1) AWS credentials from boto3 default provider chain (App Runner compatible)
    2) AWS SigV4 subject token exchanged at Google STS
    3) Service-account impersonation
    4) Domain-wide delegation subject via `subject` (GOOGLE_IMPERSONATE_USER)
    """

    settings = _resolve_wif_settings(
        subject_email_override=subject_email,
        scopes_override=scopes,
    )

    source_credentials = google_auth_aws.Credentials(
        audience=settings.audience,
        subject_token_type=AWS_SUBJECT_TOKEN_TYPE,
        token_url=settings.token_url,
        aws_security_credentials_supplier=_Boto3AwsSecurityCredentialsSupplier(),
    )

    iam_endpoint_override = None
    if settings.service_account_impersonation_url and not _looks_like_placeholder(
        settings.service_account_impersonation_url
    ):
        iam_endpoint_override = settings.service_account_impersonation_url

    delegated_credentials = impersonated_credentials.Credentials(
        source_credentials=source_credentials,
        target_principal=settings.service_account_email,
        target_scopes=list(settings.scopes),
        subject=settings.impersonate_user,
        lifetime=3600,
        iam_endpoint_override=iam_endpoint_override,
    )

    return delegated_credentials


def build_drive_client(subject_email: Optional[str] = None):
    from googleapiclient.discovery import build

    credentials = get_google_credentials(subject_email=subject_email)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def build_sheets_client(subject_email: Optional[str] = None):
    from googleapiclient.discovery import build

    credentials = get_google_credentials(subject_email=subject_email)
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)
