#!/usr/bin/env python3
"""
Simulate SES→SNS events against the local ControlHub webhook.

LocalStack's SES does not emit real delivery/open/bounce events, so this script
posts correctly-shaped SNS 'Notification' payloads to /email/webhooks/ses,
letting you exercise the full event → counter → suppression → n8n loop locally.

Usage:
  python scripts/simulate_ses_event.py delivery --message-id <id> --email a@b.com
  python scripts/simulate_ses_event.py open     --message-id <id> --email a@b.com
  python scripts/simulate_ses_event.py click    --message-id <id> --email a@b.com
  python scripts/simulate_ses_event.py bounce    --email bounce@example.com
  python scripts/simulate_ses_event.py complaint --email angry@example.com

--message-id is optional; if omitted, the latest CampaignSend for --email is used
by the webhook's recipient-matching fallback.
"""
import argparse
import json
import sys
import urllib.request

DEFAULT_URL = "http://localhost:9000/email/webhooks/ses"


def build_ses_message(event_type, message_id, email):
    mail = {
        "messageId": message_id or "sim-message-id",
        "destination": [email],
        "source": "campaigns@controlhub.local",
    }
    et = event_type.lower()
    if et == "delivery":
        return {"eventType": "Delivery", "mail": mail, "delivery": {"recipients": [email]}}
    if et == "open":
        return {"eventType": "Open", "mail": mail, "open": {"ipAddress": "127.0.0.1"}}
    if et == "click":
        return {"eventType": "Click", "mail": mail, "click": {"link": "https://example.com"}}
    if et == "bounce":
        return {"eventType": "Bounce", "mail": mail,
                "bounce": {"bounceType": "Permanent", "bounceSubType": "General",
                           "bouncedRecipients": [{"emailAddress": email}]}}
    if et == "complaint":
        return {"eventType": "Complaint", "mail": mail,
                "complaint": {"complainedRecipients": [{"emailAddress": email}]}}
    raise SystemExit(f"Unknown event type: {event_type}")


def main():
    p = argparse.ArgumentParser(description="Simulate SES/SNS events locally")
    p.add_argument("event", choices=["delivery", "open", "click", "bounce", "complaint"])
    p.add_argument("--email", required=True)
    p.add_argument("--message-id", default=None)
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--topic-arn", default="arn:aws:sns:us-east-1:000000000000:controlhub-ses-events")
    args = p.parse_args()

    ses_message = build_ses_message(args.event, args.message_id, args.email)
    sns_envelope = {
        "Type": "Notification",
        "MessageId": "sim-" + args.event,
        "TopicArn": args.topic_arn,
        "Message": json.dumps(ses_message),
        "Timestamp": "2026-07-16T00:00:00.000Z",
    }
    body = json.dumps(sns_envelope).encode()
    req = urllib.request.Request(args.url, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"{resp.status} {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
