import os
import sys
from datetime import timedelta


class Config:
    def __init__(self):
        # Resolve values at app creation time so tests/runtime env overrides are honored.
        self.ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

        # Security keys - required in production, safe defaults only for dev
        self.SECRET_KEY = os.environ.get("SECRET_KEY")
        self.JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
        self.SECRET_ENCRYPTION_KEYS = os.environ.get("SECRET_ENCRYPTION_KEYS", "")

        # Database
        self.SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI")
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False

        # JWT
        self.JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
        self.JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
        self.JWT_BLACKLIST_ENABLED = True
        self.JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]
        # Revocation safety: when the revocation store (Redis) cannot be reached,
        # fail CLOSED by default (deny) so revoked/compromised tokens cannot be
        # used during an outage. Operators may opt into a bounded degraded mode
        # by setting JWT_FAIL_OPEN=true (NOT recommended for production).
        self.JWT_FAIL_OPEN = os.environ.get("JWT_FAIL_OPEN", "false").lower() == "true"

        # CORS
        self.CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3001,http://127.0.0.1:3001")

        # Global request body cap (bytes). Prevents oversized JSON payloads;
        # uploads have their own MAX_UPLOAD_SIZE check below this ceiling.
        self.MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 64 * 1024 * 1024))

        # Redis
        self.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

        # Mail
        self.MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
        self.MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
        self.MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
        self.MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
        self.MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
        self.MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@controlhub.local")

        # Password reset
        self.PASSWORD_RESET_EXPIRES_MINUTES = int(os.environ.get("PASSWORD_RESET_EXPIRES_MINUTES", 60))

        # Registration control
        self.ALLOWED_REGISTRATION_DOMAINS = os.environ.get("ALLOWED_REGISTRATION_DOMAINS", "")

        # Feature flags (enterprise modules - default ON for development)
        self.FEATURE_SERVICE_ACCOUNTS = os.environ.get("FEATURE_SERVICE_ACCOUNTS", "true").lower() == "true"
        self.FEATURE_NOTIFICATIONS = os.environ.get("FEATURE_NOTIFICATIONS", "true").lower() == "true"
        self.FEATURE_INTEGRATIONS = os.environ.get("FEATURE_INTEGRATIONS", "true").lower() == "true"
        self.FEATURE_ASSETS = os.environ.get("FEATURE_ASSETS", "true").lower() == "true"
        self.FEATURE_PEOPLE = os.environ.get("FEATURE_PEOPLE", "true").lower() == "true"
        self.FEATURE_INTERNSHIP_PROGRAM = os.environ.get("FEATURE_INTERNSHIP_PROGRAM", "true").lower() == "true"
        self.FEATURE_AGENT_SERVICE = os.environ.get("FEATURE_AGENT_SERVICE", "true").lower() == "true"
        self.FEATURE_EMAIL_CAMPAIGNS = os.environ.get("FEATURE_EMAIL_CAMPAIGNS", "true").lower() == "true"

        # Email campaigns / SES
        self.EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", os.environ.get("STORAGE_PROVIDER", "localstack"))
        self.SES_CONFIGURATION_SET = os.environ.get("SES_CONFIGURATION_SET")
        self.SES_FROM_ADDRESS = os.environ.get("SES_FROM_ADDRESS", "campaigns@controlhub.local")
        self.SES_FROM_NAME = os.environ.get("SES_FROM_NAME", "Web Forx")
        self.SES_SENDING_ENABLED = os.environ.get("SES_SENDING_ENABLED", "true").lower() == "true"
        self.SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
        self.PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:9000")
        self.ORG_POSTAL_ADDRESS = os.environ.get("ORG_POSTAL_ADDRESS", "Web Forx Technology Limited")

        # SaaS org-management integrations (default: mock mode, no credentials needed)
        self.TAIGA_API_ENABLED = os.environ.get("TAIGA_API_ENABLED", "false").lower() == "true"
        self.TAIGA_API_URL = os.environ.get("TAIGA_API_URL", "")
        self.TAIGA_AUTH_TOKEN = os.environ.get("TAIGA_AUTH_TOKEN", "")
        self.MATTERMOST_API_ENABLED = os.environ.get("MATTERMOST_API_ENABLED", "false").lower() == "true"
        self.MATTERMOST_WEBHOOK_URL = os.environ.get("MATTERMOST_WEBHOOK_URL", "")
        self.EMAIL_NOTIFICATIONS_ENABLED = os.environ.get("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() == "true"
        self.RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
        self.RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "controlhub@notifications.webforxtech.com")

        # Agent service controls
        self.AGENT_EXPORT_APPROVAL_ROW_THRESHOLD = int(os.environ.get("AGENT_EXPORT_APPROVAL_ROW_THRESHOLD", 200))
        self.AGENT_ARTIFACT_STORAGE = os.environ.get("AGENT_ARTIFACT_STORAGE", "local")
        self.AGENT_ARTIFACTS_DIR = os.environ.get("AGENT_ARTIFACTS_DIR", "/tmp/controlhub-agent-artifacts")
        self.AGENT_ARTIFACT_URL_EXPIRY_SECONDS = int(os.environ.get("AGENT_ARTIFACT_URL_EXPIRY_SECONDS", 300))
        self.AGENT_EXTERNAL_SHEET_ALLOWLIST = os.environ.get("AGENT_EXTERNAL_SHEET_ALLOWLIST", "")
        self.ARTIFACTS_BUCKET_PREFIX = os.environ.get("ARTIFACTS_BUCKET_PREFIX", "controlhub-artifacts")
        self.ARTIFACTS_KMS_KEY_ARN = os.environ.get("ARTIFACTS_KMS_KEY_ARN")
        self.GOOGLE_WIF_AUDIENCE = os.environ.get("GOOGLE_WIF_AUDIENCE")
        self.GOOGLE_SERVICE_ACCOUNT_EMAIL = os.environ.get("GOOGLE_SERVICE_ACCOUNT_EMAIL")
        self.GOOGLE_WIF_CREDENTIALS_PATH = os.environ.get("GOOGLE_WIF_CREDENTIALS_PATH")
        self.GOOGLE_IMPERSONATE_USER = os.environ.get("GOOGLE_IMPERSONATE_USER")
        self.GOOGLE_ARTIFACTS_FOLDER_ID = os.environ.get("GOOGLE_ARTIFACTS_FOLDER_ID")
        self.GOOGLE_SCOPES = os.environ.get(
            "GOOGLE_SCOPES",
            "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/spreadsheets",
        )
        self.GOOGLE_SERVICE_ACCOUNT_IMPERSONATION_URL = os.environ.get("GOOGLE_SERVICE_ACCOUNT_IMPERSONATION_URL")

        # Legacy key-based integration vars kept for backward compatibility.
        self.GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        self.GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        self.GOOGLE_IMPERSONATED_USER = os.environ.get("GOOGLE_IMPERSONATED_USER")

    def validate(self):
        """Validate required config in production."""
        is_prod = self.ENVIRONMENT == "production"

        if is_prod:
            missing = []
            if not self.SECRET_KEY:
                missing.append("SECRET_KEY")
            if not self.JWT_SECRET_KEY:
                missing.append("JWT_SECRET_KEY")
            if not self.SQLALCHEMY_DATABASE_URI:
                missing.append("SQLALCHEMY_DATABASE_URI")
            if not self.SECRET_ENCRYPTION_KEYS:
                missing.append("SECRET_ENCRYPTION_KEYS")

            if missing:
                print(f"FATAL: Missing required env vars for production: {', '.join(missing)}", file=sys.stderr)
                sys.exit(1)

            # HS256 requires >= 32-byte keys; short keys make tokens forgeable.
            weak = [name for name, value in (("SECRET_KEY", self.SECRET_KEY), ("JWT_SECRET_KEY", self.JWT_SECRET_KEY)) if len(value) < 32]
            if weak:
                print(f"FATAL: {', '.join(weak)} must be at least 32 characters in production "
                      f"(generate with: python -c \"import secrets; print(secrets.token_hex(32))\")", file=sys.stderr)
                sys.exit(1)

            if "*" in self.CORS_ORIGINS:
                print("FATAL: CORS_ORIGINS must not contain '*' in production", file=sys.stderr)
                sys.exit(1)
        else:
            # Dev defaults - insecure but convenient
            if not self.SECRET_KEY:
                self.SECRET_KEY = "dev-secret-key-not-for-production"
            if not self.JWT_SECRET_KEY:
                self.JWT_SECRET_KEY = "dev-jwt-key-not-for-production"


def get_config():
    config = Config()
    config.validate()
    return config
