import pytest
from app.utils.integrations_mock import get_taiga_activity, send_mattermost_notification, send_email_notification
from app.models import AuditLog

def test_taiga_mock_activity():
    res = get_taiga_activity("test_user")
    assert "completed_tasks" in res
    assert "participation_score" in res
    assert res["participation_score"] > 0
    
    empty_res = get_taiga_activity("")
    assert empty_res["participation_score"] == 0

def test_mattermost_mock_notification(app):
    with app.app_context():
        success, message = send_mattermost_notification(
            username="john_doe",
            template_type="onboarding_reminder",
            context={"task_title": "Upload NDA", "due_date": "2026-07-10"}
        )
        assert success is True
        assert "Upload NDA" in message
        assert "@john_doe" in message
        
        # Verify it logged an action
        audit = AuditLog.query.filter_by(action="integration.mattermost.notify").first()
        assert audit is not None
        assert audit.target_label == "john_doe"

def test_email_mock_notification(app):
    with app.app_context():
        success, subject = send_email_notification(
            email="john@test.com",
            template_type="biweekly_reminder",
            context={"name": "John", "period_start": "2026-07-01", "period_end": "2026-07-15"}
        )
        assert success is True
        assert "Biweekly Performance Checkin" in subject
        
        # Verify audit logging
        audit = AuditLog.query.filter_by(action="integration.email.send").first()
        assert audit is not None
        assert audit.target_label == "john@test.com"
