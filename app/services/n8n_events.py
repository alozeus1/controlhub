"""
Outbound webhook emitter to n8n.

n8n owns orchestration (drip flows, scheduling, branching). ControlHub emits
signed events so n8n can react: subscriber.created, email.opened, email.bounced,
campaign.sent, etc. Best-effort — a webhook failure never breaks the caller.
"""
import os
import json
import hmac
import hashlib
import logging
import time

import requests

logger = logging.getLogger(__name__)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def emit(event_type: str, data: dict) -> None:
    """POST an event to the configured n8n webhook. No-op if not configured."""
    base = os.environ.get("N8N_BASE_URL")
    path = os.environ.get("N8N_WEBHOOK_PATH", "/webhook/controlhub-email")
    secret = os.environ.get("N8N_WEBHOOK_SECRET", "")
    if not base:
        logger.debug("n8n not configured; skipping emit %s", event_type)
        return
    payload = {"event": event_type, "data": data, "ts": int(time.time())}
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-ControlHub-Signature"] = _sign(secret, body)
    try:
        requests.post(base.rstrip("/") + path, data=body, headers=headers, timeout=5)
    except Exception as exc:
        logger.warning("n8n emit failed for %s: %s", event_type, exc)
