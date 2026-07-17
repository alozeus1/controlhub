#!/usr/bin/env python3
"""
Model / migration drift check (P0-3).

Assumes the migration chain has already been applied to the database referenced
by SQLALCHEMY_DATABASE_URI (run `flask db upgrade` first). Reflects the live
schema and compares it to the models' metadata. Exits non-zero on drift so CI
fails when a model column/table is missing from the migrations.

This is intentionally run against real PostgreSQL in CI — SQLite create_all is
NOT a substitute for validating migrations.
"""
import os
import sys
from pathlib import Path

from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    os.environ.setdefault("ENVIRONMENT", "development")
    from app import create_app
    from app.extensions import db

    app = create_app()
    with app.app_context():
        insp = inspect(db.engine)
        live_tables = set(insp.get_table_names())
        live = {t: {c["name"] for c in insp.get_columns(t)} for t in live_tables}

        expected = {t: {c.name for c in tbl.columns} for t, tbl in db.metadata.tables.items()}

        problems = []
        for t, cols in expected.items():
            if t not in live:
                problems.append(f"TABLE MISSING from DB: {t}")
                continue
            missing = cols - live[t]
            if missing:
                problems.append(f"COLUMN DRIFT in {t}: {sorted(missing)}")

        if problems:
            print("MIGRATION DRIFT DETECTED:")
            for p in problems:
                print("  -", p)
            sys.exit(1)
        print(f"OK: {len(expected)} tables match the migrated schema. No drift.")


if __name__ == "__main__":
    main()
