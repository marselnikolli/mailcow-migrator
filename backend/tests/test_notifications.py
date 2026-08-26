"""Tests for job notification dispatch (webhook + email)."""

import json

import app.core.notifications as notifications


def test_webhook_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("NOTIFY_EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert not notifications._webhook_enabled()
    assert not notifications._email_enabled()


def test_webhook_payload_posted(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.delenv("NOTIFY_EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return FakeResp()

    monkeypatch.setattr(notifications.requests, "post", fake_post)

    notifications.notify_job_event(42, "completed", "done", {"copied": 3})
    assert captured["url"] == "https://hooks.example.com/x"
    assert captured["payload"]["event"] == "completed"
    assert captured["payload"]["job_id"] == 42
    assert captured["payload"]["summary"]["copied"] == 3


def test_webhook_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://hooks.example.com/x")
    monkeypatch.delenv("NOTIFY_EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(notifications.requests, "post", boom)
    notifications.notify_job_event(1, "failed", "oops")  # should not raise


def test_email_payload_built(monkeypatch):
    monkeypatch.delenv("NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("NOTIFY_EMAIL_TO", "ops@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent["starttls"] = True

        def sendmail(self, frm, to, msg):
            sent["from"] = frm
            sent["to"] = to
            sent["msg"] = msg

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

    notifications.notify_job_event(7, "completed", "all good", {"copied": 5})
    assert sent["host"] == "smtp.example.com"
    # MIMEText base64-encodes utf-8 bodies; decode to inspect.
    from email import message_from_string
    parsed = message_from_string(sent["msg"])
    body = parsed.get_payload(decode=True).decode("utf-8")
    assert "all good" in body
    assert "copied: 5" in body
