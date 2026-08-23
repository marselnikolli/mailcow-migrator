"""Create a pre-seeded admin user.

Idempotent: safe to run multiple times. Configurable via env vars:

  SEED_ADMIN_EMAIL    default: admin@example.com
  SEED_ADMIN_PASSWORD default: admin123
  SEED_ADMIN_TENANT   default: Default

Run inside the container (or with the app's working dir on the path):

  python scripts/seed_admin.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth import AuthService
from app.db import get_db

SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "admin123")
SEED_ADMIN_TENANT = os.getenv("SEED_ADMIN_TENANT", "Default")


def seed_admin():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM tenants WHERE name = ?", (SEED_ADMIN_TENANT,))
    tenant = cursor.fetchone()
    if tenant:
        tenant_id = tenant["id"]
    else:
        cursor.execute("INSERT INTO tenants (name) VALUES (?)", (SEED_ADMIN_TENANT,))
        tenant_id = cursor.lastrowid
        print(f"Created tenant '{SEED_ADMIN_TENANT}' (id={tenant_id})")

    cursor.execute(
        "SELECT id FROM users WHERE tenant_id = ? AND email = ?",
        (tenant_id, SEED_ADMIN_EMAIL),
    )
    if cursor.fetchone():
        print(f"Admin user '{SEED_ADMIN_EMAIL}' already exists (tenant_id={tenant_id}). Nothing to do.")
        conn.close()
        return

    password_hash = AuthService.hash_password(SEED_ADMIN_PASSWORD)
    cursor.execute(
        """
        INSERT INTO users (tenant_id, email, password_hash, role, enabled)
        VALUES (?, ?, ?, 'owner', 1)
        """,
        (tenant_id, SEED_ADMIN_EMAIL, password_hash),
    )
    conn.commit()
    conn.close()
    print(f"Created admin user '{SEED_ADMIN_EMAIL}' (tenant_id={tenant_id})")


if __name__ == "__main__":
    seed_admin()
