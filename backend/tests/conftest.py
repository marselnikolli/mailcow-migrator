"""Shared pytest configuration.

Ensures required env vars are set before any app module is imported
(SECRET_KEY is mandatory outside DEBUG mode) and puts the backend dir on
sys.path so `from app...` imports resolve when running `pytest` from
backend/tests.
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("DEBUG", "True")


@pytest.fixture()
def encrypted_job_payload():
    """A job dict as it appears in the Redis queue (secrets encrypted)."""
    from app.core.secrets import SecretEncryptor
    secrets = SecretEncryptor()
    return {
        "id": 1,
        "tenant_id": 1,
        "source_email": "src@example.com",
        "source_password": secrets.encrypt("src-pass"),
        "target_email": "dst@example.com",
        "target_password": secrets.encrypt("dst-pass"),
        "source_host": "imap.example.com",
        "source_port": 993,
        "source_ssl": True,
        "target_type": "mailcow",
        "target_host": "mail.example.com",
        "target_port": 993,
        "target_ssl": True,
        "mailcow_url": "https://mail.example.com/",
        "mailcow_api_key": secrets.encrypt("api-key-123"),
        "dry_run": False,
        "sync_calendar": True,
        "sync_contacts": False,
        "retry_count": 0,
    }
