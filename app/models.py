from datetime import datetime, timedelta
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


# Role hierarchy levels (higher = more privileges)
ROLE_LEVELS = {
    "superadmin": 100,
    "admin": 50,
    "viewer": 10,
    "user": 1,
}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default="user", nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def role_level(self):
        return ROLE_LEVELS.get(self.role, 0)

    def can_manage(self, other_user):
        """Check if this user can manage another user (higher role level required)."""
        if self.role == "superadmin":
            return True
        return self.role_level > other_user.role_level

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class PasswordResetToken(db.Model):
    """Tokens for password reset flow."""
    __tablename__ = "password_reset_token"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False, unique=True)  # SHA-256 hex
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="reset_tokens")

    @property
    def is_valid(self):
        return self.used_at is None and datetime.utcnow() < self.expires_at

    @staticmethod
    def generate(user_id, expires_minutes=60):
        """Create a new reset token. Returns (token_plaintext, PasswordResetToken)."""
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        obj = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes),
        )
        return raw, obj

    @staticmethod
    def hash_token(raw):
        return hashlib.sha256(raw.encode()).hexdigest()


class FileUpload(db.Model):
    __tablename__ = "file_upload"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    
    # File info
    original_filename = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # Legacy, same as original_filename
    content_type = db.Column(db.String(100), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=True)
    
    # S3 storage
    s3_bucket = db.Column(db.String(100), nullable=False)
    s3_key = db.Column(db.String(500), nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)  # Soft delete
    
    # Relationships
    uploader = db.relationship("User", backref="uploads", foreign_keys=[user_id])
    
    @property
    def is_deleted(self):
        return self.deleted_at is not None
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "uploader_email": self.uploader.email if self.uploader else None,
            "original_filename": self.original_filename,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "s3_bucket": self.s3_bucket,
            "s3_key": self.s3_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "is_deleted": self.is_deleted,
        }

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(50), default="queued")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Policy(db.Model):
    """Defines governance policies for protected actions."""
    __tablename__ = "policy"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    action = db.Column(db.String(100), nullable=False)  # e.g., user.role_change, upload.delete
    environment = db.Column(db.String(50), default="all")  # all, production, staging
    required_role = db.Column(db.String(50), default="admin")  # Role required to perform action
    requires_approval = db.Column(db.Boolean, default=False)
    approvals_required = db.Column(db.Integer, default=1)
    approver_role = db.Column(db.String(50), default="admin")  # Role required to approve
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    creator = db.relationship("User", backref="created_policies", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "environment": self.environment,
            "required_role": self.required_role,
            "requires_approval": self.requires_approval,
            "approvals_required": self.approvals_required,
            "approver_role": self.approver_role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
            "creator_email": self.creator.email if self.creator else None,
        }


class ApprovalRequest(db.Model):
    """Tracks approval requests for protected actions."""
    __tablename__ = "approval_request"

    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("policy.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    target_label = db.Column(db.String(255), nullable=True)
    request_data = db.Column(db.JSON, nullable=True)  # Action parameters
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected, cancelled
    approvals_received = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    policy = db.relationship("Policy", backref="approval_requests")
    requester = db.relationship("User", backref="approval_requests", foreign_keys=[requester_id])

    def to_dict(self):
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "policy_name": self.policy.name if self.policy else None,
            "requester_id": self.requester_id,
            "requester_email": self.requester.email if self.requester else None,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_label": self.target_label,
            "request_data": self.request_data,
            "status": self.status,
            "approvals_received": self.approvals_received,
            "approvals_required": self.policy.approvals_required if self.policy else 1,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class ApprovalDecision(db.Model):
    """Tracks individual approval/rejection decisions."""
    __tablename__ = "approval_decision"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("approval_request.id"), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    decision = db.Column(db.String(20), nullable=False)  # approved, rejected
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    request = db.relationship("ApprovalRequest", backref="decisions")
    approver = db.relationship("User", backref="approval_decisions")

    def to_dict(self):
        return {
            "id": self.id,
            "request_id": self.request_id,
            "approver_id": self.approver_id,
            "approver_email": self.approver.email if self.approver else None,
            "decision": self.decision,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ServiceAccount(db.Model):
    """Service accounts for API access."""
    __tablename__ = "service_account"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = db.relationship("User", backref="created_service_accounts", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_active": self.is_active,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "key_count": len([k for k in self.api_keys if not k.revoked_at]),
        }


class ApiKey(db.Model):
    """API keys for service account authentication."""
    __tablename__ = "api_key"

    id = db.Column(db.Integer, primary_key=True)
    service_account_id = db.Column(db.Integer, db.ForeignKey("service_account.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    key_hash = db.Column(db.String(64), nullable=False)  # SHA-256 hash
    key_prefix = db.Column(db.String(8), nullable=False)  # First 8 chars for identification
    scopes = db.Column(db.JSON, nullable=True)  # List of allowed scopes
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    service_account = db.relationship("ServiceAccount", backref="api_keys")
    creator = db.relationship("User", backref="created_api_keys", foreign_keys=[created_by_id])

    @staticmethod
    def generate_key():
        """Generate a new API key and return (plaintext_key, key_hash, key_prefix)."""
        key = f"ch_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        key_prefix = key[:8]
        return key, key_hash, key_prefix

    @staticmethod
    def hash_key(key):
        """Hash an API key for comparison."""
        return hashlib.sha256(key.encode()).hexdigest()

    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_valid(self):
        return not self.is_expired and not self.is_revoked

    def to_dict(self):
        return {
            "id": self.id,
            "service_account_id": self.service_account_id,
            "service_account_name": self.service_account.name if self.service_account else None,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": self.scopes,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_valid": self.is_valid,
        }


class NotificationChannel(db.Model):
    """Notification channels for alerts (email, slack, webhook)."""
    __tablename__ = "notification_channel"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)  # email, slack, webhook
    name = db.Column(db.String(100), nullable=False)
    config = db.Column(db.JSON, nullable=False)  # Type-specific config (email addresses, webhook URL, etc.)
    is_enabled = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship("User", backref="created_notification_channels", foreign_keys=[created_by_id])

    def to_dict(self):
        # Mask sensitive config values
        safe_config = {}
        if self.config:
            for key, value in self.config.items():
                if key in ("webhook_url", "api_key", "token", "secret"):
                    safe_config[key] = "***masked***" if value else None
                else:
                    safe_config[key] = value
        
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "config": safe_config,
            "is_enabled": self.is_enabled,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlertRule(db.Model):
    """Rules that trigger alerts based on events."""
    __tablename__ = "alert_rule"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    event_type = db.Column(db.String(50), nullable=False)  # job.failed, user.disabled, etc.
    severity = db.Column(db.String(20), default="medium")  # low, medium, high, critical
    conditions = db.Column(db.JSON, nullable=True)  # Optional conditions for filtering
    channel_ids = db.Column(db.JSON, nullable=False)  # List of channel IDs to notify
    is_enabled = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship("User", backref="created_alert_rules", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "event_type": self.event_type,
            "severity": self.severity,
            "conditions": self.conditions,
            "channel_ids": self.channel_ids,
            "is_enabled": self.is_enabled,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlertEvent(db.Model):
    """History of triggered alerts."""
    __tablename__ = "alert_event"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("alert_rule.id"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    payload = db.Column(db.JSON, nullable=True)
    channels_notified = db.Column(db.JSON, nullable=True)  # List of channel IDs that were notified
    delivery_status = db.Column(db.String(20), default="pending")  # pending, delivered, failed, partial
    delivery_details = db.Column(db.JSON, nullable=True)  # Per-channel delivery status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rule = db.relationship("AlertRule", backref="events")

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "rule_name": self.rule.name if self.rule else None,
            "event_type": self.event_type,
            "severity": self.severity,
            "title": self.title,
            "payload": self.payload,
            "channels_notified": self.channels_notified,
            "delivery_status": self.delivery_status,
            "delivery_details": self.delivery_details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Integration(db.Model):
    """External integrations (webhooks, SIEM, etc.)."""
    __tablename__ = "integration"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(30), nullable=False)  # webhook, siem, s3_export
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    config = db.Column(db.JSON, nullable=False)  # Type-specific config
    events = db.Column(db.JSON, nullable=True)  # List of event types to send (null = all)
    is_enabled = db.Column(db.Boolean, default=True)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    failure_count = db.Column(db.Integer, default=0)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship("User", backref="created_integrations", foreign_keys=[created_by_id])

    def to_dict(self):
        # Mask sensitive config values
        safe_config = {}
        if self.config:
            for key, value in self.config.items():
                if key in ("url", "webhook_url", "endpoint"):
                    safe_config[key] = value  # URLs are okay to show
                elif key in ("secret", "api_key", "token", "password", "access_key", "secret_key"):
                    safe_config[key] = "***masked***" if value else None
                else:
                    safe_config[key] = value

        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "config": safe_config,
            "events": self.events,
            "is_enabled": self.is_enabled,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "failure_count": self.failure_count,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class IntegrationLog(db.Model):
    """Logs of integration deliveries."""
    __tablename__ = "integration_log"

    id = db.Column(db.Integer, primary_key=True)
    integration_id = db.Column(db.Integer, db.ForeignKey("integration.id"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    payload_summary = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False)  # success, failed, skipped
    response_code = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    integration = db.relationship("Integration", backref="logs")

    def to_dict(self):
        return {
            "id": self.id,
            "integration_id": self.integration_id,
            "integration_name": self.integration.name if self.integration else None,
            "event_type": self.event_type,
            "payload_summary": self.payload_summary,
            "status": self.status,
            "response_code": self.response_code,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditExportJob(db.Model):
    """Scheduled or on-demand audit log export jobs."""
    __tablename__ = "audit_export_job"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    export_format = db.Column(db.String(20), nullable=False)  # csv, json, jsonl
    destination_type = db.Column(db.String(20), nullable=False)  # s3, download
    destination_config = db.Column(db.JSON, nullable=True)  # S3 bucket, path, etc.
    filters = db.Column(db.JSON, nullable=True)  # Date range, actions, etc.
    schedule = db.Column(db.String(50), nullable=True)  # Cron expression or null for one-time
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_run_status = db.Column(db.String(20), nullable=True)  # success, failed
    last_run_records = db.Column(db.Integer, nullable=True)
    is_enabled = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = db.relationship("User", backref="created_audit_exports", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "export_format": self.export_format,
            "destination_type": self.destination_type,
            "destination_config": self.destination_config,
            "filters": self.filters,
            "schedule": self.schedule,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_status": self.last_run_status,
            "last_run_records": self.last_run_records,
            "is_enabled": self.is_enabled,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Asset(db.Model):
    """IT assets for inventory tracking (light CMDB)."""
    __tablename__ = "asset"

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(50), unique=True, nullable=False)  # e.g., ASSET-001
    name = db.Column(db.String(100), nullable=False)
    asset_type = db.Column(db.String(30), nullable=False)  # server, laptop, network, software, other
    status = db.Column(db.String(20), default="active")  # active, inactive, maintenance, retired
    description = db.Column(db.Text, nullable=True)
    
    # Location and assignment
    location = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    
    # Technical details
    manufacturer = db.Column(db.String(100), nullable=True)
    model = db.Column(db.String(100), nullable=True)
    serial_number = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    mac_address = db.Column(db.String(17), nullable=True)
    
    # Lifecycle
    purchase_date = db.Column(db.Date, nullable=True)
    warranty_expiry = db.Column(db.Date, nullable=True)
    
    # Custom attributes
    attributes = db.Column(db.JSON, nullable=True)  # Flexible key-value pairs
    tags = db.Column(db.JSON, nullable=True)  # List of tags for categorization
    
    # Tracking
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    assigned_to = db.relationship("User", backref="assigned_assets", foreign_keys=[assigned_to_id])
    creator = db.relationship("User", backref="created_assets", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "asset_tag": self.asset_tag,
            "name": self.name,
            "asset_type": self.asset_type,
            "status": self.status,
            "description": self.description,
            "location": self.location,
            "department": self.department,
            "assigned_to_id": self.assigned_to_id,
            "assigned_to_email": self.assigned_to.email if self.assigned_to else None,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial_number": self.serial_number,
            "ip_address": self.ip_address,
            "mac_address": self.mac_address,
            "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
            "warranty_expiry": self.warranty_expiry.isoformat() if self.warranty_expiry else None,
            "attributes": self.attributes,
            "tags": self.tags,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AssetHistory(db.Model):
    """Tracks changes to assets over time."""
    __tablename__ = "asset_history"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)
    action = db.Column(db.String(30), nullable=False)  # created, updated, assigned, unassigned, status_changed
    changes = db.Column(db.JSON, nullable=True)  # What changed
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    actor_email = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    asset = db.relationship("Asset", backref="history")
    actor = db.relationship("User", backref="asset_changes", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "asset_tag": self.asset.asset_tag if self.asset else None,
            "action": self.action,
            "changes": self.changes,
            "actor_id": self.actor_id,
            "actor_email": self.actor_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    """Tracks all significant actions in the system for compliance and debugging."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    actor_email = db.Column(db.String(120), nullable=True)  # Denormalized for query speed
    action = db.Column(db.String(50), nullable=False)  # e.g., user.created, user.login
    target_type = db.Column(db.String(50), nullable=True)  # e.g., user, upload, job
    target_id = db.Column(db.Integer, nullable=True)
    target_label = db.Column(db.String(255), nullable=True)  # Human-readable (e.g., email)
    details = db.Column(db.JSON, nullable=True)  # Additional context (renamed from metadata)
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to actor
    actor = db.relationship("User", backref="audit_logs", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "actor_id": self.actor_id,
            "actor_email": self.actor_email,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_label": self.target_label,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }