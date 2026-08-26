"""Tests for imapsync command construction and the redaction helper."""

from app.core.imapsync import ImapsyncWrapper
from app.core.worker import _redact


def test_build_cmd_defaults():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="src@example.com", source_password="sp",
        target_email="dst@example.com", target_password="tp",
    )
    assert "--host1=imap.gmail.com" in cmd
    assert "--port1=993" in cmd
    assert "--user1=src@example.com" in cmd
    assert "--password1=sp" in cmd
    assert "--host2=localhost" in cmd
    assert "--port2=993" in cmd
    assert "--user2=dst@example.com" in cmd
    assert "--password2=tp" in cmd
    assert "--ssl1" in cmd
    assert "--ssl2" in cmd
    assert "--all" in cmd
    assert "--dry" not in cmd


def test_build_cmd_dry_run():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
        dry_run=True,
    )
    assert "--dry" in cmd


def test_build_cmd_ssl_off():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
        source_ssl=False, target_ssl=False,
    )
    assert "--nossl1" in cmd
    assert "--nossl2" in cmd
    assert "--ssl1" not in cmd
    assert "--ssl2" not in cmd


def test_build_cmd_custom_hosts():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
        source_host="src.example.com", source_port=993,
        target_host="mail.example.com", target_port=993,
    )
    assert "--host1=src.example.com" in cmd
    assert "--host2=mail.example.com" in cmd


def test_build_cmd_folders():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
        folders="INBOX, Sent, Archive",
    )
    assert "--include=INBOX" in cmd
    assert "--include=Sent" in cmd
    assert "--include=Archive" in cmd


def test_build_cmd_maxage_and_since():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
        maxage_days=30, since_date="2026-01-01",
    )
    assert "--maxage=30" in cmd
    assert "--since=2026-01-01" in cmd


def test_build_cmd_no_filters_by_default():
    cmd = ImapsyncWrapper._build_cmd(
        source_email="s", source_password="a", target_email="t", target_password="b",
    )
    assert not any(f.startswith("--include=") for f in cmd)
    assert not any(f.startswith("--maxage=") for f in cmd)
    assert not any(f.startswith("--since=") for f in cmd)


def test_redact_removes_exact_secrets():
    text = "login failed for src-pass and api-key-123"
    result = _redact(text, ["src-pass", "api-key-123"])
    assert "src-pass" not in result
    assert "api-key-123" not in result
    assert "login failed" in result


def test_redact_handles_regex_special_chars():
    # A password with regex-special characters that would break naive masking.
    text = "password is NpTzUK-5Gyhng-=G8i here"
    result = _redact(text, ["NpTzUK-5Gyhng-=G8i"])
    assert "NpTzUK-5Gyhng-=G8i" not in result


def test_redact_ignores_empty_secrets():
    text = "keep this"
    assert _redact(text, ["", None]) == "keep this"
