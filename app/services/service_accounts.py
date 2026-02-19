"""
Service Account Service Layer

Business logic for service accounts and API keys.
"""
import hmac
from datetime import datetime
from typing import Optional, Tuple, List

from app.extensions import db
from app.models import ServiceAccount, ApiKey, User
from app.utils.audit import log_action


class ServiceAccountService:
    """Service for managing service accounts."""

    @staticmethod
    def list_accounts(
        page: int = 1,
        page_size: int = 20,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> dict:
        """List service accounts with pagination and filters."""
        query = ServiceAccount.query

        if is_active is not None:
            query = query.filter(ServiceAccount.is_active == is_active)

        if search:
            query = query.filter(ServiceAccount.name.ilike(f"%{search}%"))

        query = query.order_by(ServiceAccount.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [sa.to_dict() for sa in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_account(account_id: int) -> Optional[ServiceAccount]:
        """Get a service account by ID."""
        return ServiceAccount.query.get(account_id)

    @staticmethod
    def create_account(
        name: str,
        description: Optional[str],
        actor: User,
    ) -> ServiceAccount:
        """Create a new service account."""
        account = ServiceAccount(
            name=name,
            description=description,
            is_active=True,
            created_by_id=actor.id,
        )
        db.session.add(account)
        db.session.commit()

        log_action(
            action="service_account.created",
            actor=actor,
            target_type="service_account",
            target_id=account.id,
            target_label=account.name,
        )

        return account

    @staticmethod
    def update_account(
        account: ServiceAccount,
        actor: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Tuple[ServiceAccount, dict]:
        """Update a service account. Returns (account, changes)."""
        changes = {}

        if name is not None and account.name != name:
            changes["name"] = {"from": account.name, "to": name}
            account.name = name

        if description is not None and account.description != description:
            changes["description"] = {"from": account.description, "to": description}
            account.description = description

        if is_active is not None and account.is_active != is_active:
            changes["is_active"] = {"from": account.is_active, "to": is_active}
            account.is_active = is_active

        if changes:
            db.session.commit()
            action = "service_account.activated" if is_active else "service_account.deactivated" if is_active is False else "service_account.updated"
            log_action(
                action=action,
                actor=actor,
                target_type="service_account",
                target_id=account.id,
                target_label=account.name,
                details={"changes": changes},
            )

        return account, changes


class ApiKeyService:
    """Service for managing API keys."""

    @staticmethod
    def list_keys(
        service_account_id: int,
        include_revoked: bool = False,
    ) -> List[dict]:
        """List API keys for a service account."""
        query = ApiKey.query.filter(ApiKey.service_account_id == service_account_id)

        if not include_revoked:
            query = query.filter(ApiKey.revoked_at.is_(None))

        query = query.order_by(ApiKey.created_at.desc())
        return [key.to_dict() for key in query.all()]

    @staticmethod
    def create_key(
        service_account: ServiceAccount,
        name: str,
        actor: User,
        scopes: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> Tuple[ApiKey, str]:
        """
        Create a new API key.
        
        Returns (api_key, plaintext_key). The plaintext key is only available once!
        """
        plaintext_key, key_hash, key_prefix = ApiKey.generate_key()

        api_key = ApiKey(
            service_account_id=service_account.id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or [],
            expires_at=expires_at,
            created_by_id=actor.id,
        )
        db.session.add(api_key)
        db.session.commit()

        log_action(
            action="api_key.created",
            actor=actor,
            target_type="api_key",
            target_id=api_key.id,
            target_label=f"{service_account.name}/{name}",
            details={
                "key_prefix": key_prefix,
                "scopes": scopes,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )

        return api_key, plaintext_key

    @staticmethod
    def get_key(key_id: int) -> Optional[ApiKey]:
        """Get an API key by ID."""
        return ApiKey.query.get(key_id)

    @staticmethod
    def revoke_key(api_key: ApiKey, actor: User) -> ApiKey:
        """Revoke an API key."""
        if api_key.revoked_at:
            raise ValueError("Key is already revoked")

        api_key.revoked_at = datetime.utcnow()
        db.session.commit()

        log_action(
            action="api_key.revoked",
            actor=actor,
            target_type="api_key",
            target_id=api_key.id,
            target_label=f"{api_key.service_account.name}/{api_key.name}",
            details={"key_prefix": api_key.key_prefix},
        )

        return api_key

    @staticmethod
    def validate_key(key: str) -> Optional[ApiKey]:
        """
        Validate an API key and return the ApiKey if valid.
        Updates last_used_at on successful validation.
        
        Uses constant-time comparison to prevent timing attacks.
        Checks: key exists, not revoked, not expired, service account active.
        """
        if not key:
            return None

        key_hash = ApiKey.hash_key(key)
        
        # Find all keys and use constant-time comparison
        # This prevents timing attacks from hash lookup
        api_key = None
        for candidate in ApiKey.query.all():
            if hmac.compare_digest(candidate.key_hash, key_hash):
                api_key = candidate
                break

        if not api_key:
            return None

        # Explicit check: key must not be revoked
        if api_key.revoked_at is not None:
            return None

        # Explicit check: key must not be expired
        if api_key.is_expired:
            return None

        # Explicit check: service account must be active
        if not api_key.service_account or not api_key.service_account.is_active:
            return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()
        db.session.commit()

        return api_key

    @staticmethod
    def check_scope(api_key: ApiKey, required_scope: str) -> bool:
        """Check if an API key has the required scope."""
        if not api_key.scopes:
            return True  # No scopes = full access
        
        if "*" in api_key.scopes:
            return True
        
        # Check for exact match or wildcard
        for scope in api_key.scopes:
            if scope == required_scope:
                return True
            if scope.endswith(".*"):
                prefix = scope[:-2]
                if required_scope.startswith(prefix):
                    return True
        
        return False
