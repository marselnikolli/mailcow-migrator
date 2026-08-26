"""Tests for job payload defaulting logic in routes/jobs.py."""

from app.models import JobCreate
from app.routes.jobs import _apply_defaults


def test_defaults_mirror_source_to_target():
    job = _apply_defaults(JobCreate(
        source_email="user@src.example.com",
        source_password="src-pass",
    ))
    assert job.target_email == "user@src.example.com"
    assert job.target_password == "src-pass"


def test_target_type_defaults_to_mailcow_when_explicitly_empty():
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="p",
        target_type="",
        mailcow_url="https://mail.example.com",
        mailcow_api_key="key",
    ))
    assert job.target_type == "mailcow"


def test_target_type_stays_imap_when_explicitly_set():
    # Pydantic defaults target_type to "imap", so passing only mailcow_url
    # does not silently upgrade it; the caller must set target_type explicitly.
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="p",
        mailcow_url="https://mail.example.com",
        mailcow_api_key="key",
    ))
    assert job.target_type == "imap"


def test_target_type_defaults_to_imap_without_url():
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="p",
    ))
    assert job.target_type == "imap"


def test_mailcow_localhost_host_replaced_with_mailcow_hostname():
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="p",
        target_type="mailcow",
        target_server={"host": "localhost", "port": 993, "ssl": True},
        mailcow_url="https://mail.example.com/",
    ))
    assert job.target_server.host == "mail.example.com"


def test_explicit_target_host_preserved():
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="p",
        target_type="mailcow",
        target_server={"host": "smtp.example.net", "port": 993, "ssl": True},
        mailcow_url="https://mail.example.com/",
    ))
    assert job.target_server.host == "smtp.example.net"


def test_explicit_target_password_and_email_respected():
    job = _apply_defaults(JobCreate(
        source_email="a@b.com",
        source_password="src-pass",
        target_email="new@b.com",
        target_password="dst-pass",
    ))
    assert job.target_email == "new@b.com"
    assert job.target_password == "dst-pass"
