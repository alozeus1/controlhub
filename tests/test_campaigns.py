"""
Tests for the Email Campaigns module.

Runs against SQLite with SES in dry-run (SES_SENDING_ENABLED=false) and
synchronous send (CAMPAIGN_SEND_SYNC=true), so no LocalStack/Redis is needed.
"""
import json
import pytest


@pytest.fixture
def email_env(monkeypatch):
    monkeypatch.setenv("FEATURE_EMAIL_CAMPAIGNS", "true")
    monkeypatch.setenv("SES_SENDING_ENABLED", "false")   # dry-run: synthetic message ids
    monkeypatch.setenv("CAMPAIGN_SEND_SYNC", "true")     # run send inline
    monkeypatch.setenv("EMAIL_PROVIDER", "localstack")


@pytest.fixture
def admin(create_user):
    return create_user("admin@webforx.tech", role="admin")


def _seed_list_with_subs(app, emails):
    from app.extensions import db
    from app.models import EmailList
    from app.services.campaigns import SubscriberService, ListService
    with app.app_context():
        lst = EmailList(name="Test List")
        db.session.add(lst)
        db.session.commit()
        lid = lst.id
        for e in emails:
            s, _ = SubscriberService.upsert(e, name=e.split("@")[0])
            ListService.add_member(lid, s.id)
        return lid


def test_feature_flag_gate(app, client, email_env, admin, auth_header):
    # Feature flags are read from app.config (resolved at app creation), so
    # flip the live config to simulate the module being disabled.
    app.config["FEATURE_EMAIL_CAMPAIGNS"] = False
    r = client.get("/admin/email/subscribers", headers=auth_header(admin))
    assert r.status_code == 403
    assert r.get_json()["code"] == "FEATURE_DISABLED"
    app.config["FEATURE_EMAIL_CAMPAIGNS"] = True


def test_create_subscriber_and_list(client, email_env, admin, auth_header):
    r = client.post("/admin/email/subscribers",
                    headers=auth_header(admin),
                    json={"email": "Ada@Example.com", "name": "Ada"})
    assert r.status_code in (200, 201)
    assert r.get_json()["email"] == "ada@example.com"   # normalized lower-case

    r = client.post("/admin/email/lists", headers=auth_header(admin),
                    json={"name": "Newsletter"})
    assert r.status_code == 201
    assert r.get_json()["member_count"] == 0


def test_invalid_email_rejected(client, email_env, admin, auth_header):
    r = client.post("/admin/email/subscribers", headers=auth_header(admin),
                    json={"email": "not-an-email"})
    assert r.status_code == 400


def test_send_campaign_filters_suppression(app, client, email_env, admin, auth_header):
    lid = _seed_list_with_subs(app, ["a@example.com", "b@example.com", "c@example.com"])

    # Suppress one recipient up-front.
    client.post("/admin/email/suppressions", headers=auth_header(admin),
                json={"email": "c@example.com", "reason": "manual"})

    r = client.post("/admin/email/campaigns", headers=auth_header(admin),
                    json={"name": "Launch", "subject": "Hi {{name}}",
                          "html": "<p>Hello {{name}}</p>", "target_list_id": lid})
    cid = r.get_json()["id"]

    r = client.post(f"/admin/email/campaigns/{cid}/send", headers=auth_header(admin))
    assert r.status_code == 200
    body = r.get_json()
    assert body["recipients"] == 2          # suppressed 'c' excluded
    # Sync mode (CAMPAIGN_SEND_SYNC=true) completes the send inline.
    assert body["status"] in ("sending", "sent")

    r = client.get(f"/admin/email/campaigns/{cid}", headers=auth_header(admin))
    c = r.get_json()
    assert c["status"] == "sent"
    assert c["sent_count"] == 2


def test_ses_webhook_bounce_suppresses(app, client, email_env, admin, auth_header):
    lid = _seed_list_with_subs(app, ["bounce-me@example.com"])
    r = client.post("/admin/email/campaigns", headers=auth_header(admin),
                    json={"name": "C", "subject": "S", "html": "<p>x</p>", "target_list_id": lid})
    cid = r.get_json()["id"]
    client.post(f"/admin/email/campaigns/{cid}/send", headers=auth_header(admin))

    # Grab the message id from the send record.
    from app.models import CampaignSend
    with app.app_context():
        mid = CampaignSend.query.filter_by(campaign_id=cid).first().ses_message_id

    sns = {
        "Type": "Notification",
        "TopicArn": "arn:aws:sns:us-east-1:000000000000:controlhub-ses-events",
        "Message": json.dumps({
            "eventType": "Bounce",
            "mail": {"messageId": mid, "destination": ["bounce-me@example.com"]},
            "bounce": {"bounceType": "Permanent",
                       "bouncedRecipients": [{"emailAddress": "bounce-me@example.com"}]},
        }),
    }
    r = client.post("/email/webhooks/ses", json=sns)
    assert r.status_code == 200

    # Now suppressed.
    from app.services.campaigns import SuppressionService
    with app.app_context():
        assert SuppressionService.is_suppressed("bounce-me@example.com")


def test_one_click_unsubscribe(app, client, email_env, admin, auth_header):
    from app.models import Subscriber
    from app.services.campaigns import SubscriberService
    with app.app_context():
        sub, _ = SubscriberService.upsert("leaver@example.com", name="Bye")
        token = sub.unsubscribe_token

    r = client.post(f"/email/unsubscribe/{token}")
    assert r.status_code == 200
    assert r.get_json()["unsubscribed"] is True

    with app.app_context():
        assert Subscriber.query.filter_by(email="leaver@example.com").first().status == "unsubscribed"


def test_webhook_rejects_wrong_topic(client, email_env, monkeypatch):
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:111:expected")
    sns = {"Type": "Notification", "TopicArn": "arn:aws:sns:us-east-1:999:evil",
           "Message": json.dumps({"eventType": "Delivery", "mail": {"messageId": "x"}})}
    r = client.post("/email/webhooks/ses", json=sns)
    assert r.status_code == 403
