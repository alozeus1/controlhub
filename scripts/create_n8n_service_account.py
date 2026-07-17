#!/usr/bin/env python3
"""
Provision a ControlHub service account + API key for n8n.

n8n authenticates to ControlHub's email endpoints with this key via the
`X-API-Key` header (service-account auth is already wired into require_role,
granting admin-level access to the campaigns API).

The plaintext key is printed ONCE — copy it into an n8n Header Auth credential.

Usage (inside the api container or a venv with the app importable):
    python scripts/create_n8n_service_account.py
    python scripts/create_n8n_service_account.py --name "n8n Drip Bot" --expires-days 365
"""
import argparse
import sys
from datetime import datetime, timedelta


def main():
    p = argparse.ArgumentParser(description="Create a service account + API key for n8n")
    p.add_argument("--name", default="n8n Email Orchestrator")
    p.add_argument("--key-name", default="n8n-primary")
    p.add_argument("--expires-days", type=int, default=0, help="0 = no expiry")
    p.add_argument("--actor-email", default=None,
                   help="Admin/superadmin email to attribute creation to (defaults to first superadmin)")
    args = p.parse_args()

    from app import create_app
    from app.models import User, ServiceAccount
    from app.services.service_accounts import ServiceAccountService, ApiKeyService

    app = create_app()
    with app.app_context():
        # Pick an actor to own the record.
        actor = None
        if args.actor_email:
            actor = User.query.filter_by(email=args.actor_email).first()
            if not actor:
                print(f"ERROR: no user with email {args.actor_email}", file=sys.stderr)
                sys.exit(1)
        if not actor:
            actor = (User.query.filter_by(role="superadmin", is_active=True).first()
                     or User.query.filter_by(role="admin", is_active=True).first())
        if not actor:
            print("ERROR: no superadmin/admin user found. Create one first.", file=sys.stderr)
            sys.exit(1)

        # Reuse an existing service account of this name, else create it.
        account = ServiceAccount.query.filter_by(name=args.name).first()
        if not account:
            account = ServiceAccountService.create_account(
                name=args.name,
                description="Used by n8n to orchestrate email drip campaigns via the ControlHub API.",
                actor=actor,
            )

        expires_at = None
        if args.expires_days > 0:
            expires_at = datetime.utcnow() + timedelta(days=args.expires_days)

        api_key, plaintext = ApiKeyService.create_key(
            service_account=account,
            name=args.key_name,
            actor=actor,
            scopes=["email:read", "email:write", "email:send"],
            expires_at=expires_at,
        )

        print("\n" + "=" * 68)
        print("  n8n service account + API key created")
        print("=" * 68)
        print(f"  Service account : {account.name} (id={account.id})")
        print(f"  Key name        : {api_key.name}")
        print(f"  Key prefix      : {api_key.key_prefix}")
        print(f"  Expires         : {expires_at.isoformat() if expires_at else 'never'}")
        print(f"  Owner           : {actor.email}")
        print("-" * 68)
        print("  API KEY (shown ONCE — store it in n8n now):")
        print(f"\n    {plaintext}\n")
        print("  In n8n → Credentials → 'Header Auth':")
        print("    Name  : X-API-Key")
        print("    Value : <the key above>")
        print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
