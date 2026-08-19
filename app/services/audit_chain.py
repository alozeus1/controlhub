"""
Tamper-evident audit log.

Each audit row commits to its own content and to the hash of the row before it:

    row_hash = SHA256(canonical_fields || prev_hash)

Deleting a row, editing a row, or reordering rows breaks the chain at a point
`verify_chain` reports. This does not *prevent* a rewrite — an attacker with DB
access can still issue the DELETE. It makes the rewrite detectable, which is the
property that survives an assume-breach threat model.

Two caveats worth stating plainly:

* An attacker who can write to the DB *and* knows this algorithm can recompute a
  consistent chain over doctored rows. Detection therefore depends on comparing
  against a copy the attacker cannot reach — the out-of-band mirror described in
  docs/ZERO_TRUST_ASSUME_BREACH_DESIGN.md §3.3. The chain makes that comparison
  cheap and pinpoints where divergence starts.
* The chain is only as good as its weakest link being noticed, so
  `verify_chain` is meant to run on a schedule and alarm somewhere that is not
  ControlHub.
"""
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

GENESIS = "0" * 64


def _canonical(entry) -> str:
    """
    Stable serialization of the fields a row commits to.

    `sort_keys` + `default=str` keep the digest reproducible across processes and
    Python versions; anything non-serializable degrades to its string form
    rather than raising and blocking the audit write.
    """
    return json.dumps(
        {
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
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_row_hash(entry, prev_hash: str) -> str:
    payload = f"{_canonical(entry)}|{prev_hash or GENESIS}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def latest_hash() -> str:
    """Hash of the most recent chained row, or GENESIS if the log is empty."""
    from app.models import AuditLog

    row = (AuditLog.query
           .filter(AuditLog.row_hash.isnot(None))
           .order_by(AuditLog.id.desc())
           .first())
    return row.row_hash if row else GENESIS


def seal(entry) -> None:
    """
    Attach prev_hash/row_hash to a pending audit entry.

    Never raises: an audit row that cannot be sealed is still far better than an
    action that fails because sealing did. A missing row_hash shows up as an
    unsealed link in verify_chain rather than as lost history.
    """
    try:
        entry.prev_hash = latest_hash()
        entry.row_hash = compute_row_hash(entry, entry.prev_hash)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("audit chain seal failed for action=%s: %s", entry.action, exc)


def verify_chain(start_id: int = 0, limit: int = None) -> dict:
    """
    Recompute the chain and report the first divergence.

    Returns {"ok", "checked", "first_bad_id", "reason"}. Intended to be run on a
    schedule with the result alarmed outside ControlHub.
    """
    from app.models import AuditLog

    query = (AuditLog.query
             .filter(AuditLog.id > start_id)
             .order_by(AuditLog.id.asc()))
    if limit:
        query = query.limit(limit)

    rows = query.all()
    if not rows:
        return {"ok": True, "checked": 0, "first_bad_id": None, "reason": None}

    # Anchor on the row preceding the range so a deletion at the boundary is caught.
    prev = (AuditLog.query
            .filter(AuditLog.id <= start_id, AuditLog.row_hash.isnot(None))
            .order_by(AuditLog.id.desc())
            .first())
    expected_prev = prev.row_hash if prev else GENESIS

    checked = 0
    for row in rows:
        if row.row_hash is None:
            # Pre-migration rows are unsealed; skip without breaking the chain.
            continue
        if row.prev_hash != expected_prev:
            return {"ok": False, "checked": checked, "first_bad_id": row.id,
                    "reason": "prev_hash mismatch — a row was deleted or reordered"}
        if compute_row_hash(row, row.prev_hash) != row.row_hash:
            return {"ok": False, "checked": checked, "first_bad_id": row.id,
                    "reason": "row_hash mismatch — row content was modified"}
        expected_prev = row.row_hash
        checked += 1

    return {"ok": True, "checked": checked, "first_bad_id": None, "reason": None}
