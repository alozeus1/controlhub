"""Google Workspace publishing helpers for Agent artifacts."""

import csv
import io
import json
import os


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _load_service_account_info():
    info_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    info_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")

    if info_json:
        return json.loads(info_json)
    if info_file:
        with open(info_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    raise ValueError("Google service account credentials are not configured")


def _credentials(subject_email=None):
    from google.oauth2 import service_account

    info = _load_service_account_info()
    credentials = service_account.Credentials.from_service_account_info(info, scopes=GOOGLE_SCOPES)

    subject = subject_email or os.environ.get("GOOGLE_IMPERSONATED_USER")
    if subject:
        credentials = credentials.with_subject(subject)
    return credentials


def _drive_service(subject_email=None):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=_credentials(subject_email), cache_discovery=False)


def _sheets_service(subject_email=None):
    from googleapiclient.discovery import build

    return build("sheets", "v4", credentials=_credentials(subject_email), cache_discovery=False)


def publish_to_drive(file_bytes, filename, mime_type, folder_id, subject_email=None):
    """Upload a generated artifact to a Google Drive folder."""
    from googleapiclient.http import MediaInMemoryUpload

    service = _drive_service(subject_email)

    metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaInMemoryUpload(file_bytes, mimetype=mime_type, resumable=False)

    response = (
        service.files()
        .create(body=metadata, media_body=media, fields="id,name,webViewLink")
        .execute()
    )
    return {
        "drive_file_id": response.get("id"),
        "name": response.get("name"),
        "web_view_link": response.get("webViewLink"),
    }


def _parse_rows_from_artifact(file_bytes, mime_type):
    if mime_type in {"text/csv", "application/csv"}:
        text = file_bytes.decode("utf-8")
        reader = csv.reader(io.StringIO(text))
        return [list(row) for row in reader]

    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        from openpyxl import load_workbook

        workbook = load_workbook(filename=io.BytesIO(file_bytes), read_only=True)
        sheet = workbook.active
        rows = []
        for row in sheet.iter_rows(values_only=True):
            rows.append([value for value in row])
        return rows

    # Fallback: one-column data
    text = file_bytes.decode("utf-8")
    return [[line] for line in text.splitlines()]


def publish_to_sheet(file_bytes, mime_type, spreadsheet_id, sheet_name, a1_range, mode="overwrite", subject_email=None):
    """Publish artifact tabular data into Google Sheets."""
    if mode not in {"overwrite", "append"}:
        raise ValueError("mode must be overwrite or append")

    service = _sheets_service(subject_email)
    rows = _parse_rows_from_artifact(file_bytes, mime_type)

    target_range = f"{sheet_name}!{a1_range}" if sheet_name else a1_range

    if mode == "overwrite":
        result = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=target_range,
                valueInputOption="RAW",
                body={"values": rows},
            )
            .execute()
        )
        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows"),
            "updated_columns": result.get("updatedColumns"),
            "updated_cells": result.get("updatedCells"),
        }

    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=target_range,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updates = result.get("updates", {})
    return {
        "updated_range": updates.get("updatedRange"),
        "updated_rows": updates.get("updatedRows"),
        "updated_columns": updates.get("updatedColumns"),
        "updated_cells": updates.get("updatedCells"),
    }
