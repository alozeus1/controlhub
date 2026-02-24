import os
import sys
from datetime import timedelta


class Config:
    ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

    # Security keys - required in production, safe defaults only for dev
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///controlhub.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT
    JWT_ACCESS_TOKEN_EXPIRES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES", 3600))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_BLACKLIST_ENABLED = True
    JWT_BLACKLIST_TOKEN_CHECKS = ["access", "refresh"]

    # Auth mode: local | cognito | hybrid
    AUTH_MODE = os.environ.get("AUTH_MODE", "hybrid").lower()

    # Local auth hardening
    MAX_FAILED_LOGIN_ATTEMPTS = int(os.environ.get("MAX_FAILED_LOGIN_ATTEMPTS", 5))
    ACCOUNT_LOCKOUT_MINUTES = int(os.environ.get("ACCOUNT_LOCKOUT_MINUTES", 15))
    REQUIRE_EMAIL_VERIFICATION = os.environ.get("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"

    # Cognito configuration
    COGNITO_REGION = os.environ.get("COGNITO_REGION", "")
    COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
    COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")
    COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "")
    COGNITO_JWKS_URL = os.environ.get("COGNITO_JWKS_URL", "")
    COGNITO_ISSUER = os.environ.get("COGNITO_ISSUER", "")
    COGNITO_JWKS_CACHE_SECONDS = int(os.environ.get("COGNITO_JWKS_CACHE_SECONDS", 3600))
    COGNITO_AUTO_PROVISION = os.environ.get("COGNITO_AUTO_PROVISION", "false").lower() == "true"
    COGNITO_ALLOW_EMAIL_LINKING = os.environ.get("COGNITO_ALLOW_EMAIL_LINKING", "true").lower() == "true"
    COGNITO_HEALTHCHECK_JWKS = os.environ.get("COGNITO_HEALTHCHECK_JWKS", "false").lower() == "true"

    # Frontend hosted-ui callback / SSO prep
    COGNITO_REDIRECT_URI = os.environ.get("COGNITO_REDIRECT_URI", "http://localhost:3001/ui/auth/callback")

    # CORS
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3001,http://127.0.0.1:3001")

    # Redis
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@controlhub.local")

    # Password reset
    PASSWORD_RESET_EXPIRES_MINUTES = int(os.environ.get("PASSWORD_RESET_EXPIRES_MINUTES", 60))

    # Registration control
    ALLOWED_REGISTRATION_DOMAINS = os.environ.get("ALLOWED_REGISTRATION_DOMAINS", "")

    # Feature flags (enterprise modules - default ON for development)
    FEATURE_SERVICE_ACCOUNTS = os.environ.get("FEATURE_SERVICE_ACCOUNTS", "true").lower() == "true"
    FEATURE_NOTIFICATIONS = os.environ.get("FEATURE_NOTIFICATIONS", "true").lower() == "true"
    FEATURE_INTEGRATIONS = os.environ.get("FEATURE_INTEGRATIONS", "true").lower() == "true"
    FEATURE_ASSETS = os.environ.get("FEATURE_ASSETS", "true").lower() == "true"

    @classmethod
    def validate(cls):
        """Validate required config in production."""
        is_prod = cls.ENVIRONMENT == "production"

        if is_prod:
            missing = []
            if not cls.SECRET_KEY:
                missing.append("SECRET_KEY")
            if not cls.JWT_SECRET_KEY:
                missing.append("JWT_SECRET_KEY")
            if not cls.SQLALCHEMY_DATABASE_URI:
                missing.append("SQLALCHEMY_DATABASE_URI")

            if missing:
                print(f"FATAL: Missing required env vars for production: {', '.join(missing)}", file=sys.stderr)
                sys.exit(1)
        else:
            # Dev defaults - insecure but convenient
            if not cls.SECRET_KEY:
                cls.SECRET_KEY = "dev-secret-key-not-for-production"
            if not cls.JWT_SECRET_KEY:
                cls.JWT_SECRET_KEY = "dev-jwt-key-not-for-production"


def get_config():
    Config.validate()
    if Config.COGNITO_REGION and Config.COGNITO_USER_POOL_ID:
        if not Config.COGNITO_ISSUER:
            Config.COGNITO_ISSUER = (
                f"https://cognito-idp.{Config.COGNITO_REGION}.amazonaws.com/{Config.COGNITO_USER_POOL_ID}"
            )
        if not Config.COGNITO_JWKS_URL:
            Config.COGNITO_JWKS_URL = f"{Config.COGNITO_ISSUER}/.well-known/jwks.json"
    return Config()
