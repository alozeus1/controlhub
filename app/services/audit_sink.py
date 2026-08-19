"""
Out-of-band audit mirror.

The hash chain in audit_chain.py makes tampering *detectable*; this module is
what makes that detection meaningful. It ships sealed audit rows to a sink
ControlHub cannot rewrite, so there is a second copy to compare against when the
in-database chain and the mirror disagree.

Design notes:

* **Shipping is a separate pass, not part of the audit write.** Coupling delivery
  to `log_action` would make every audited action fail (or hang) when the sink is
  unreachable. Instead a high-water mark is persisted and `mirror_pending()` runs
  on a short interval — "within seconds" is a cron frequency, not a synchronous
  call.
* **The mark only advances on confirmed delivery**, so a sink outage causes replay
  from the last acknowledged row rather than a silent gap.
* Sinks are append-oriented. For CloudWatch Logs, pair this with a resource policy
  denying Delete*; for S3, use Object Lock in compliance mode. Without that
  server-side protection the mirror is only a convenience copy — the append-only
  guarantee lives in the sink's configuration, not in this code.
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

MARK_KEY = "audit_mirror_high_water"


def sink_name() -> str:
    """Configured sink: 'cloudwatch', 'file', or 'none' (default)."""
    return (os.environ.get("AUDIT_MIRROR_SINK") or "none").strip().lower()


def mirror_enabled() -> bool:
    return sink_name() not in ("", "none")


# ─── High-water mark ──────────────────────────────────────────────────────────

def get_high_water() -> int:
    from app.models import SystemState

    row = SystemState.query.filter_by(key=MARK_KEY).first()
    try:
        return int(row.value) if row and row.value else 0
    except (TypeError, ValueError):
        return 0


def set_high_water(audit_id: int) -> None:
    from app.extensions import db
    from app.models import SystemState

    row = SystemState.query.filter_by(key=MARK_KEY).first()
    if row is None:
        row = SystemState(key=MARK_KEY, value=str(audit_id))
        db.session.add(row)
    else:
        row.value = str(audit_id)
    db.session.commit()


# ─── Serialization ────────────────────────────────────────────────────────────

def serialize(entry) -> str:
    """
    One JSON line per audit row, including the chain hashes.

    The hashes travel with the record so the mirrored copy can be re-verified
    independently — that is what turns the mirror into evidence rather than a
    second, equally-rewritable log.
    """
    return json.dumps({
        "id": entry.id,
        "actor_id": entry.actor_id,
        "actor_email": entry.actor_email,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "target_label": entry.target_label,
        "details": entry.details,
        "ip_address": entry.ip_address,
        "user_agent": entry.user_agent,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "prev_hash": entry.prev_hash,
        "row_hash": entry.row_hash,
    }, sort_keys=True, separators=(",", ":"), default=str)


# ─── Sinks ────────────────────────────────────────────────────────────────────

def _ship_file(lines):
    """Local append-only-ish file sink. Dev and small deployments only."""
    path = os.environ.get("AUDIT_MIRROR_FILE", "/var/log/controlhub/audit-mirror.jsonl")
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(lines)


def _ship_cloudwatch(lines):
    """
    CloudWatch Logs sink.

    Protect the destination with a resource policy denying logs:DeleteLogGroup /
    DeleteLogStream for the application's role, otherwise the same credential
    that can rewrite the DB can erase the mirror too.
    """
    import boto3
    from botocore.config import Config as BotoConfig

    group = os.environ.get("AUDIT_MIRROR_LOG_GROUP", "/controlhub/audit")
    stream = os.environ.get("AUDIT_MIRROR_LOG_STREAM", "audit-chain")

    kwargs = {
        "service_name": "logs",
        "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        "config": BotoConfig(retries={"max_attempts": 3, "mode": "standard"}),
    }
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if (os.environ.get("STORAGE_PROVIDER", "localstack") == "localstack") and endpoint:
        kwargs["endpoint_url"] = endpoint
        kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")

    client = boto3.client(**kwargs)
    for create, args in (("create_log_group", {"logGroupName": group}),
                         ("create_log_stream", {"logGroupName": group,
                                                "logStreamName": stream})):
        try:
            getattr(client, create)(**args)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

    # CloudWatch requires ascending timestamps; the audit rows are already in id
    # order, so reuse a single wall-clock stamp for the batch.
    import time
    now = int(time.time() * 1000)
    client.put_log_events(
        logGroupName=group,
        logStreamName=stream,
        logEvents=[{"timestamp": now, "message": line} for line in lines],
    )
    return len(lines)


SINKS = {"file": _ship_file, "cloudwatch": _ship_cloudwatch}


# ─── Driver ───────────────────────────────────────────────────────────────────

def mirror_pending(batch_size: int = 500) -> dict:
    """
    Ship audit rows newer than the high-water mark.

    Returns {"shipped", "high_water", "sink", "error"}. Never raises: a mirror
    failure must not take down whatever scheduled it. The mark is advanced only
    after the sink confirms, so a failure replays rather than skips.
    """
    from app.models import AuditLog

    sink = sink_name()
    if not mirror_enabled():
        return {"shipped": 0, "high_water": get_high_water(), "sink": sink, "error": None}

    ship = SINKS.get(sink)
    if ship is None:
        return {"shipped": 0, "high_water": get_high_water(), "sink": sink,
                "error": f"unknown AUDIT_MIRROR_SINK: {sink}"}

    mark = get_high_water()
    rows = (AuditLog.query
            .filter(AuditLog.id > mark)
            .order_by(AuditLog.id.asc())
            .limit(batch_size)
            .all())
    if not rows:
        return {"shipped": 0, "high_water": mark, "sink": sink, "error": None}

    try:
        ship([serialize(r) for r in rows])
    except Exception as exc:
        logger.error("audit mirror shipping failed at id>%s: %s", mark, exc)
        return {"shipped": 0, "high_water": mark, "sink": sink, "error": str(exc)}

    new_mark = rows[-1].id
    set_high_water(new_mark)
    logger.info("audit mirror shipped %s rows to %s (high_water=%s)",
                len(rows), sink, new_mark)
    return {"shipped": len(rows), "high_water": new_mark, "sink": sink, "error": None}
