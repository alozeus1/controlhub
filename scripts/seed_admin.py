#!/usr/bin/env python3
"""
Seed script to create an admin user.

Usage:
    # From host (with venv activated):
    SQLALCHEMY_DATABASE_URI=postgresql://postgres:password@localhost:5432/flaskdb python scripts/seed_admin.py

    # From Docker:
    docker compose exec api python scripts/seed_admin.py
"""
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import User

# Default admin credentials (override with env vars)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def seed_admin():
    app = create_app()

    with app.app_context():
        # Check if admin already exists
        existing = User.query.filter_by(email=ADMIN_EMAIL).first()
        if existing:
            print(f"User {ADMIN_EMAIL} already exists (id={existing.id}, role={existing.role})")
            if existing.role != "admin":
                existing.role = "admin"
                db.session.commit()
                print(f"Updated role to 'admin'")
            return

        # Create admin user
        admin = User(email=ADMIN_EMAIL, role="admin")
        admin.set_password(ADMIN_PASSWORD)

        db.session.add(admin)
        db.session.commit()

        print(f"Created admin user:")
        print(f"  Email: {ADMIN_EMAIL}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print(f"  Role: admin")


if __name__ == "__main__":
    seed_admin()
