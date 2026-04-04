#!/usr/bin/env python3
"""Smoke test for Google WIF + DWD integration."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value in {"...", "<set-in-secrets-manager>"}:
        raise RuntimeError(
            f"Missing {name}. Configure runtime env vars (recommended via secrets manager)."
        )
    return value


def _next_steps(message: str, status: int | str = "unknown") -> list[str]:
    lower = message.lower()
    steps = []

    if "delegation" in lower or "sub" in lower or "not authorized to access this resource/api" in lower:
        steps.append(
            "DWD likely missing: in admin.google.com -> Security -> API controls -> "
            "Domain-wide delegation, add the service-account client ID with scopes:\n"
            "https://www.googleapis.com/auth/drive.file, https://www.googleapis.com/auth/spreadsheets"
        )

    if "audience" in lower or "invalid_target" in lower or "workloadidentitypool" in lower:
        steps.append(
            "WIF audience looks incorrect. Expected format:\n"
            "//iam.googleapis.com/projects/<project-number>/locations/global/"
            "workloadIdentityPools/<pool-id>/providers/<provider-id>"
        )

    if "workloadidentityuser" in lower or "iam.serviceaccounts.getaccesstoken" in lower or "permission denied" in lower:
        steps.append(
            "AWS principal may not be authorized. Grant the AWS identity permission "
            "`roles/iam.workloadIdentityUser` on the target service account."
        )

    if "no aws credentials" in lower or "unable to locate credentials" in lower:
        steps.append(
            "AWS credentials missing. Provide credentials via default AWS SDK provider chain "
            "(env vars, shared config, or App Runner task role)."
        )

    if status in {401, 403} and not steps:
        steps.append(
            "Check IAM bindings for WIF principal -> service account impersonation and verify DWD approval."
        )

    return steps


def pretty_http_error(exc: HttpError) -> str:
    body = ""
    try:
        body = exc.content.decode("utf-8", errors="replace")
    except Exception:
        body = str(exc)

    status = getattr(exc.resp, "status", "unknown")
    steps = _next_steps(body, status=status)
    message = f"HTTP {status}: {body}"
    if steps:
        message += "\nNext steps:\n- " + "\n- ".join(steps)
    return message


def pretty_runtime_error(exc: Exception) -> str:
    text = str(exc)
    steps = _next_steps(text)
    message = text
    if steps:
        message += "\nNext steps:\n- " + "\n- ".join(steps)
    return message


def main() -> int:
    load_dotenv(ROOT / ".env")

    try:
        require_env("GOOGLE_WIF_AUDIENCE")
        require_env("GOOGLE_SERVICE_ACCOUNT_EMAIL")
        require_env("GOOGLE_IMPERSONATE_USER")
        require_env("GOOGLE_SCOPES")
        folder_id = require_env("GOOGLE_ARTIFACTS_FOLDER_ID")
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    from app.integrations.google_auth import build_drive_client

    try:
        drive = build_drive_client()
    except Exception as exc:
        print(
            "[ERROR] Unable to initialize Google credentials:\n"
            f"{pretty_runtime_error(exc)}",
            file=sys.stderr,
        )
        return 2

    content = (
        "ControlHub WIF connectivity check\n"
        f"timestamp_utc={datetime.now(timezone.utc).isoformat()}\n"
    ).encode("utf-8")
    media = MediaInMemoryUpload(content, mimetype="text/plain", resumable=False)
    filename = f"controlhub-wif-test-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"

    try:
        created = (
            drive.files()
            .create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media,
                fields="id,name,parents",
            )
            .execute()
        )
    except HttpError as exc:
        print(f"[ERROR] Google Drive upload failed: {pretty_http_error(exc)}", file=sys.stderr)
        return 3

    print(f"SUCCESS: Uploaded file {created.get('name')} id={created.get('id')}")
    print(f"parents={created.get('parents')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
