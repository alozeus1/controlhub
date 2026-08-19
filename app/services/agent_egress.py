"""
The single chokepoint every artifact passes through on its way out of ControlHub.

Two holes this closes, both of which matter specifically because the attacker is
assumed to already hold elevated access:

1. **Destinations were self-defining.** `_validate_destination_payload` checks the
   *shape* of a destination config, not its value — any Drive folder id or
   spreadsheet id was accepted. An attacker with admin access could therefore
   create a destination pointing at storage they control and publish to it
   through the normal, fully-audited, approval-satisfying flow. The fix is an
   allowlist of real target ids that lives in **deployment configuration, not the
   database**: compromising the application does not grant the ability to add a
   new egress target, because that requires changing env and redeploying.

2. **Time-of-check/time-of-use.** An approved request stores a destination *id*,
   and the config behind that id was resolved fresh at publish time. An admin
   could get a benign destination approved and then repoint it. Requests now pin
   a fingerprint of the resolved target at creation; publishing re-computes it
   and refuses on drift.

Everything that leaves goes through `deliver()`. If you add a new egress path,
route it here — a second exit is a second thing to audit and a second thing to
forget.
"""
import hashlib
import logging
import os

logger = logging.getLogger(__name__)


class EgressDenied(Exception):
    """Raised when a delivery fails a chokepoint check. Never caught locally."""

    def __init__(self, message, code="EGRESS_DENIED", details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


# ─── Deployment-level target allowlist ────────────────────────────────────────

def _csv_env(name):
    return {item.strip() for item in (os.environ.get(name, "") or "").split(",") if item.strip()}


def allowed_drive_folders() -> set:
    return _csv_env("AGENT_EGRESS_DRIVE_FOLDERS")


def allowed_sheets() -> set:
    return _csv_env("AGENT_EGRESS_SHEETS")


def egress_allowlist_configured() -> bool:
    return bool(allowed_drive_folders() or allowed_sheets())


def resolve_target(destination):
    """
    (kind, target_id) for a destination — the thing data actually lands in.

    Deliberately reads the live config rather than a cached copy, so the
    fingerprint comparison in `deliver()` sees any drift.
    """
    config = destination.config or {}
    if destination.destination_type == "google_drive_folder":
        target = (config.get("folder_id") or "").strip()
        if not target:
            raise EgressDenied("google_drive_folder destination is missing folder_id",
                               code="EGRESS_MISCONFIGURED")
        return "drive_folder", target
    if destination.destination_type == "google_sheet_range":
        target = (config.get("spreadsheet_id") or "").strip()
        if not target:
            raise EgressDenied("google_sheet_range destination is missing spreadsheet_id",
                               code="EGRESS_MISCONFIGURED")
        return "spreadsheet", target
    raise EgressDenied(f"Unsupported destination type: {destination.destination_type}",
                       code="EGRESS_UNSUPPORTED_TYPE")


def destination_fingerprint(destination) -> str:
    """
    Stable digest of *where data goes* — type plus resolved target id.

    Intentionally excludes cosmetic fields (name, allowed_template_ids) so
    renaming a destination does not invalidate approved requests, while
    repointing one does.
    """
    kind, target = resolve_target(destination)
    return hashlib.sha256(f"{kind}:{target}".encode("utf-8")).hexdigest()


def assert_target_allowlisted(destination):
    """
    Enforce the deployment-level allowlist.

    When no allowlist is configured this permits delivery and warns — the same
    posture as the other Phase 2 hardening switches, so upgrading does not break
    a working deployment. Configure it in production; the whole control is inert
    until you do.
    """
    kind, target = resolve_target(destination)

    if not egress_allowlist_configured():
        logger.warning(
            "AGENT_EGRESS_* allowlist is not configured — publishing to %s '%s' without "
            "a deployment-level check. Anyone who can create a destination can choose "
            "where data goes.", kind, target)
        return kind, target

    allowed = allowed_drive_folders() if kind == "drive_folder" else allowed_sheets()
    if target not in allowed:
        raise EgressDenied(
            f"Destination target '{target}' is not in the deployment egress allowlist.",
            code="EGRESS_TARGET_NOT_ALLOWLISTED",
            details={"kind": kind, "target": target},
        )
    return kind, target


def impersonation_identity(destination):
    """
    The Google identity this delivery writes as.

    Prefers a per-destination identity so a destination writes as a narrowly
    scoped principal instead of one ambient account used for everything. Falls
    back to the global env identity. Recorded in the audit event either way —
    "which identity wrote this" is the first question during an investigation.
    """
    per_destination = (destination.config or {}).get("impersonate_user")
    return (per_destination
            or os.environ.get("GOOGLE_IMPERSONATE_USER")
            or os.environ.get("GOOGLE_IMPERSONATED_USER"))


# ─── Scope integrity ──────────────────────────────────────────────────────────

def assert_scope_integrity(rows, template):
    """
    Verify the rows about to be serialized carry no field outside the template.

    `enforce_template_fields` already projects to the allowed set; this re-checks
    the result immediately before it becomes bytes. The point is defense in
    depth: field scope is the boundary between "an approved report" and "a data
    leak", and it should not rest on one call being correct forever.
    """
    allowed = set(template.allowed_fields or [])
    if not allowed:
        return
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        leaked = set(row.keys()) - allowed
        if leaked:
            raise EgressDenied(
                f"Row contains fields outside the template scope: {sorted(leaked)}",
                code="EGRESS_SCOPE_VIOLATION",
                details={"unexpected_fields": sorted(leaked),
                         "template_id": getattr(template, "id", None)},
            )


# ─── The chokepoint ───────────────────────────────────────────────────────────

def deliver(artifact, destination, actor=None, mode="overwrite", expected_fingerprint=None):
    """
    Publish an artifact externally. The only sanctioned way out.

    Order matters: every cheap check that can deny runs before the bytes are
    read, and the audit event is written with the *resolved* target rather than
    the destination id, so the record says where data actually went.
    """
    from app.services.agent_tools import (
        publish_to_drive, publish_to_sheet, read_artifact_bytes,
    )
    from app.utils.audit import log_action

    if not destination or not destination.is_active:
        raise EgressDenied("Destination not found or inactive", code="EGRESS_DESTINATION_INACTIVE")

    agent_request = artifact.request
    if not agent_request:
        raise EgressDenied("Artifact has no originating request", code="EGRESS_NO_REQUEST")

    if agent_request.template_id not in (destination.allowed_template_ids or []):
        raise EgressDenied("template_id is not allowed for selected destination",
                           code="EGRESS_TEMPLATE_NOT_ALLOWED")

    kind, target = assert_target_allowlisted(destination)

    # TOCTOU: the destination must still point where it did when this request
    # was created and approved.
    pinned = expected_fingerprint or getattr(agent_request, "destination_fingerprint", None)
    current = destination_fingerprint(destination)
    if pinned and pinned != current:
        log_action(
            action="agent.egress.destination_changed",
            actor=actor,
            target_type="generated_artifact",
            target_id=artifact.id,
            target_label=artifact.filename,
            details={"destination_id": destination.id, "kind": kind,
                     "pinned_fingerprint": pinned, "current_fingerprint": current},
        )
        raise EgressDenied(
            "This destination has been modified since the request was approved. "
            "Re-submit the request.",
            code="EGRESS_DESTINATION_CHANGED",
            details={"destination_id": destination.id},
        )

    identity = impersonation_identity(destination)
    artifact_bytes = read_artifact_bytes(artifact.s3_bucket, artifact.s3_key)

    if kind == "drive_folder":
        result = publish_to_drive(artifact_bytes, artifact, destination)
    else:
        result = publish_to_sheet(artifact_bytes, artifact, destination, mode=mode)

    log_action(
        action="agent.artifact.published_external",
        actor=actor,
        target_type="generated_artifact",
        target_id=artifact.id,
        target_label=artifact.filename,
        details={
            "agent_request_id": artifact.agent_request_id,
            "destination_id": destination.id,
            "destination_type": destination.destination_type,
            # The resolved target, not just the id — the id is an indirection an
            # attacker controls; this is the fact you want in the record.
            "egress_kind": kind,
            "egress_target": target,
            "egress_identity": identity,
            "allowlist_enforced": egress_allowlist_configured(),
            "template_id": agent_request.template_id,
            "row_count": artifact.row_count,
            "sha256": artifact.sha256,
            "result": result,
        },
    )
    return result
