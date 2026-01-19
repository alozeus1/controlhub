from datetime import datetime
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

class FileUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    s3_key = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(200), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    status = db.Column(db.String(50), default="queued")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


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