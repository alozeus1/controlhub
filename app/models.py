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


# ─── SECRETS MANAGER ─────────────────────────────────────────────────────────

import base64
from cryptography.fernet import Fernet

class Secret(db.Model):
    __tablename__ = "secret"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    project = db.Column(db.String(100), nullable=True)
    environment = db.Column(db.String(50), nullable=True)  # dev/staging/prod/all
    value_encrypted = db.Column(db.Text, nullable=False)  # Fernet encrypted
    tags = db.Column(db.JSON, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    last_rotated_at = db.Column(db.DateTime, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship("User", backref="created_secrets", foreign_keys=[created_by_id])

    def to_dict(self, include_value=False):
        d = {
            "id": self.id, "name": self.name, "description": self.description,
            "project": self.project, "environment": self.environment,
            "tags": self.tags,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_rotated_at": self.last_rotated_at.isoformat() if self.last_rotated_at else None,
            "created_by_id": self.created_by_id,
            "creator_email": self.creator.email if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_value:
            d["value"] = self.value_encrypted  # caller must decrypt
        return d

class SecretAccessLog(db.Model):
    __tablename__ = "secret_access_log"
    id = db.Column(db.Integer, primary_key=True)
    secret_id = db.Column(db.Integer, db.ForeignKey("secret.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # read, update, delete
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    secret = db.relationship("Secret", backref="access_logs")
    user = db.relationship("User", backref="secret_access_logs")
    def to_dict(self):
        return {"id": self.id, "secret_id": self.secret_id, "user_email": self.user.email if self.user else None,
                "action": self.action, "ip_address": self.ip_address,
                "created_at": self.created_at.isoformat() if self.created_at else None}

# ─── ENVIRONMENT CONFIG MANAGER ──────────────────────────────────────────────

class EnvProject(db.Model):
    __tablename__ = "env_project"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship("User", backref="created_env_projects", foreign_keys=[created_by_id])
    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class EnvConfig(db.Model):
    __tablename__ = "env_config"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("env_project.id"), nullable=False)
    environment = db.Column(db.String(50), nullable=False)  # dev, staging, prod
    key = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Text, nullable=True)
    is_secret = db.Column(db.Boolean, default=False)  # mask in UI
    description = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project = db.relationship("EnvProject", backref="configs")
    creator = db.relationship("User", foreign_keys=[created_by_id])
    updater = db.relationship("User", foreign_keys=[updated_by_id])
    __table_args__ = (db.UniqueConstraint("project_id", "environment", "key", name="uq_env_config"),)
    def to_dict(self, show_secrets=False):
        val = self.value if (show_secrets or not self.is_secret) else "***"
        return {"id": self.id, "project_id": self.project_id, "environment": self.environment,
                "key": self.key, "value": val, "is_secret": self.is_secret,
                "description": self.description, "created_by_id": self.created_by_id,
                "updated_by_id": self.updated_by_id,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

# ─── INCIDENT MANAGEMENT ─────────────────────────────────────────────────────

class Incident(db.Model):
    __tablename__ = "incident"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    severity = db.Column(db.String(10), nullable=False, default="p3")  # p1,p2,p3,p4
    status = db.Column(db.String(20), nullable=False, default="open")  # open,investigating,resolved,closed
    affected_services = db.Column(db.JSON, nullable=True)
    commander_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    root_cause = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    commander = db.relationship("User", backref="commanded_incidents", foreign_keys=[commander_id])
    creator = db.relationship("User", backref="created_incidents", foreign_keys=[created_by_id])
    def to_dict(self):
        return {"id": self.id, "title": self.title, "description": self.description,
                "severity": self.severity, "status": self.status,
                "affected_services": self.affected_services,
                "commander_id": self.commander_id,
                "commander_email": self.commander.email if self.commander else None,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
                "root_cause": self.root_cause,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

class IncidentUpdate(db.Model):
    __tablename__ = "incident_update"
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status_change = db.Column(db.String(20), nullable=True)  # new status if changed
    posted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    incident = db.relationship("Incident", backref="updates")
    poster = db.relationship("User", backref="incident_updates")
    def to_dict(self):
        return {"id": self.id, "incident_id": self.incident_id, "message": self.message,
                "status_change": self.status_change,
                "posted_by_id": self.posted_by_id,
                "poster_email": self.poster.email if self.poster else None,
                "created_at": self.created_at.isoformat() if self.created_at else None}

# ─── RUNBOOK / WIKI ───────────────────────────────────────────────────────────

class Runbook(db.Model):
    __tablename__ = "runbook"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    content_md = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(100), nullable=True)
    tags = db.Column(db.JSON, nullable=True)
    is_published = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship("User", backref="created_runbooks", foreign_keys=[created_by_id])
    updater = db.relationship("User", backref="updated_runbooks", foreign_keys=[updated_by_id])
    def to_dict(self):
        return {"id": self.id, "title": self.title, "slug": self.slug,
                "content_md": self.content_md, "category": self.category, "tags": self.tags,
                "is_published": self.is_published,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "updated_by_id": self.updated_by_id,
                "updater_email": self.updater.email if self.updater else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

# ─── DEPLOYMENT TRACKER ───────────────────────────────────────────────────────

class Deployment(db.Model):
    __tablename__ = "deployment"
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.String(100), nullable=False)
    environment = db.Column(db.String(50), nullable=False)  # dev,staging,prod
    status = db.Column(db.String(20), default="success")  # success,failed,in_progress,rolled_back
    is_rollback = db.Column(db.Boolean, default=False)
    deployed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    deployed_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    pipeline_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    deployer = db.relationship("User", backref="deployments", foreign_keys=[deployed_by_id])
    def to_dict(self):
        return {"id": self.id, "service_name": self.service_name, "version": self.version,
                "environment": self.environment, "status": self.status,
                "is_rollback": self.is_rollback,
                "deployed_by_id": self.deployed_by_id,
                "deployer_email": self.deployer.email if self.deployer else None,
                "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
                "notes": self.notes, "pipeline_url": self.pipeline_url,
                "created_at": self.created_at.isoformat() if self.created_at else None}

# ─── CERTIFICATE TRACKER ──────────────────────────────────────────────────────

class Certificate(db.Model):
    __tablename__ = "certificate"
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), nullable=False)
    issuer = db.Column(db.String(255), nullable=True)
    environment = db.Column(db.String(50), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    auto_renew = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship("User", backref="created_certificates", foreign_keys=[created_by_id])
    @property
    def days_until_expiry(self):
        return (self.expires_at - datetime.utcnow()).days
    @property
    def status(self):
        d = self.days_until_expiry
        if d < 0: return "expired"
        if d <= 7: return "critical"
        if d <= 30: return "warning"
        return "ok"
    def to_dict(self):
        return {"id": self.id, "domain": self.domain, "issuer": self.issuer,
                "environment": self.environment,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "days_until_expiry": self.days_until_expiry, "status": self.status,
                "auto_renew": self.auto_renew, "notes": self.notes, "tags": self.tags,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

# ─── FEATURE FLAGS ────────────────────────────────────────────────────────────

class FeatureFlag(db.Model):
    __tablename__ = "feature_flag"
    id = db.Column(db.Integer, primary_key=True)
    project = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    key = db.Column(db.String(100), nullable=False)  # slug-style key
    description = db.Column(db.Text, nullable=True)
    flag_type = db.Column(db.String(20), default="boolean")  # boolean, percentage
    value = db.Column(db.JSON, nullable=True)  # true/false or 0-100
    is_enabled = db.Column(db.Boolean, default=False)
    environments = db.Column(db.JSON, nullable=True)  # per-env overrides {dev: true, prod: false}
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship("User", backref="created_feature_flags", foreign_keys=[created_by_id])
    __table_args__ = (db.UniqueConstraint("project", "key", name="uq_feature_flag"),)
    def to_dict(self):
        return {"id": self.id, "project": self.project, "name": self.name, "key": self.key,
                "description": self.description, "flag_type": self.flag_type,
                "value": self.value, "is_enabled": self.is_enabled,
                "environments": self.environments,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

# ─── LICENSE TRACKER ──────────────────────────────────────────────────────────

class License(db.Model):
    __tablename__ = "license"
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(100), nullable=False)
    product = db.Column(db.String(100), nullable=False)
    license_type = db.Column(db.String(50), nullable=True)  # per-seat, site, subscription
    seats = db.Column(db.Integer, nullable=True)
    seats_used = db.Column(db.Integer, nullable=True)
    cost_monthly = db.Column(db.Numeric(12, 2), nullable=True)
    renewal_date = db.Column(db.Date, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="active")  # active, expired, cancelled
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner = db.relationship("User", backref="owned_licenses", foreign_keys=[owner_id])
    creator = db.relationship("User", backref="created_licenses", foreign_keys=[created_by_id])
    @property
    def days_until_renewal(self):
        if not self.renewal_date:
            return None
        from datetime import date
        return (self.renewal_date - date.today()).days
    def to_dict(self):
        return {"id": self.id, "vendor": self.vendor, "product": self.product,
                "license_type": self.license_type, "seats": self.seats,
                "seats_used": self.seats_used,
                "cost_monthly": float(self.cost_monthly) if self.cost_monthly else None,
                "renewal_date": self.renewal_date.isoformat() if self.renewal_date else None,
                "days_until_renewal": self.days_until_renewal,
                "owner_id": self.owner_id,
                "owner_email": self.owner.email if self.owner else None,
                "notes": self.notes, "status": self.status,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

# ─── ONBOARDING / OFFBOARDING WORKFLOWS ──────────────────────────────────────

class WorkflowTemplate(db.Model):
    __tablename__ = "workflow_template"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    workflow_type = db.Column(db.String(20), nullable=False)  # onboarding, offboarding, custom
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship("User", backref="created_workflow_templates", foreign_keys=[created_by_id])
    def to_dict(self):
        return {"id": self.id, "name": self.name, "workflow_type": self.workflow_type,
                "description": self.description, "is_active": self.is_active,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "step_count": len(self.steps)}

class WorkflowTemplateStep(db.Model):
    __tablename__ = "workflow_template_step"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("workflow_template.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    assignee_role = db.Column(db.String(50), nullable=True)  # role to assign to
    template = db.relationship("WorkflowTemplate", backref="steps")
    def to_dict(self):
        return {"id": self.id, "template_id": self.template_id, "order": self.order,
                "title": self.title, "description": self.description,
                "assignee_role": self.assignee_role}

class WorkflowRun(db.Model):
    __tablename__ = "workflow_run"
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("workflow_template.id"), nullable=False)
    subject_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    subject_name = db.Column(db.String(200), nullable=True)  # for non-user subjects
    status = db.Column(db.String(20), default="active")  # active, completed, cancelled
    started_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    template = db.relationship("WorkflowTemplate", backref="runs")
    subject_user = db.relationship("User", backref="workflow_runs_as_subject", foreign_keys=[subject_user_id])
    starter = db.relationship("User", backref="started_workflow_runs", foreign_keys=[started_by_id])
    def to_dict(self):
        completed = sum(1 for s in self.run_steps if s.status == "completed")
        total = len(self.run_steps)
        return {"id": self.id, "template_id": self.template_id,
                "template_name": self.template.name if self.template else None,
                "workflow_type": self.template.workflow_type if self.template else None,
                "subject_user_id": self.subject_user_id,
                "subject_email": self.subject_user.email if self.subject_user else None,
                "subject_name": self.subject_name,
                "status": self.status,
                "started_by_id": self.started_by_id,
                "starter_email": self.starter.email if self.starter else None,
                "progress": {"completed": completed, "total": total},
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None}

class WorkflowRunStep(db.Model):
    __tablename__ = "workflow_run_step"
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("workflow_run.id"), nullable=False)
    template_step_id = db.Column(db.Integer, db.ForeignKey("workflow_template_step.id"), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending, completed, skipped
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    run = db.relationship("WorkflowRun", backref="run_steps")
    assigned_to = db.relationship("User", backref="assigned_workflow_steps", foreign_keys=[assigned_to_id])
    completed_by = db.relationship("User", backref="completed_workflow_steps", foreign_keys=[completed_by_id])
    def to_dict(self):
        return {"id": self.id, "run_id": self.run_id, "order": self.order,
                "title": self.title, "description": self.description, "status": self.status,
                "assigned_to_id": self.assigned_to_id,
                "assigned_to_email": self.assigned_to.email if self.assigned_to else None,
                "completed_by_id": self.completed_by_id,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "notes": self.notes}

# ─── COST ALLOCATION ──────────────────────────────────────────────────────────

class CostEntry(db.Model):
    __tablename__ = "cost_entry"
    id = db.Column(db.Integer, primary_key=True)
    cloud_provider = db.Column(db.String(30), nullable=False)  # aws, gcp, azure, other
    service_name = db.Column(db.String(100), nullable=False)  # EC2, RDS, etc.
    team = db.Column(db.String(100), nullable=True)
    project = db.Column(db.String(100), nullable=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    period = db.Column(db.String(7), nullable=False)  # YYYY-MM
    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship("User", backref="created_cost_entries", foreign_keys=[created_by_id])
    def to_dict(self):
        return {"id": self.id, "cloud_provider": self.cloud_provider,
                "service_name": self.service_name, "team": self.team, "project": self.project,
                "amount": float(self.amount), "currency": self.currency,
                "period": self.period, "notes": self.notes,
                "created_by_id": self.created_by_id,
                "creator_email": self.creator.email if self.creator else None,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class BudgetRequest(db.Model):
    __tablename__ = "budget_request"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    team = db.Column(db.String(100), nullable=True)
    project = db.Column(db.String(100), nullable=True)
    amount_requested = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    justification = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    requester = db.relationship("User", backref="budget_requests", foreign_keys=[requested_by_id])
    reviewer = db.relationship("User", backref="reviewed_budget_requests", foreign_keys=[reviewed_by_id])
    def to_dict(self):
        return {"id": self.id, "title": self.title, "team": self.team, "project": self.project,
                "amount_requested": float(self.amount_requested), "currency": self.currency,
                "justification": self.justification, "status": self.status,
                "reviewed_by_id": self.reviewed_by_id,
                "reviewer_email": self.reviewer.email if self.reviewer else None,
                "review_notes": self.review_notes,
                "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
                "requested_by_id": self.requested_by_id,
                "requester_email": self.requester.email if self.requester else None,
                "created_at": self.created_at.isoformat() if self.created_at else None}