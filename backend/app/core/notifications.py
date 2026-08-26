"""Job completion/failure notifications via generic webhook and/or SMTP email.

Configured entirely via environment variables so no UI/DB changes are needed:
  NOTIFY_WEBHOOK_URL      - optional, POSTed a JSON payload on job completion/failure
  NOTIFY_EMAIL_TO         - optional, comma-separated recipients
  NOTIFY_EMAIL_FROM       - sender address (default NOTIFY_EMAIL_TO[0])
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_STARTTLS
"""

import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _webhook_enabled() -> bool:
    return bool(os.getenv("NOTIFY_WEBHOOK_URL"))


def _email_enabled() -> bool:
    return bool(os.getenv("NOTIFY_EMAIL_TO") and os.getenv("SMTP_HOST"))


def notify_job_event(job_id: int, event: str, message: str,
                     summary: Optional[dict] = None) -> None:
    """Send a webhook POST and/or email for a job lifecycle event.

    Args:
        job_id: database job id
        event: 'started' | 'completed' | 'failed' | 'cancelled'
        message: human-readable status line
        summary: optional dict of report-style summary numbers
    """
    payload = {
        "event": event,
        "job_id": job_id,
        "message": message,
        "summary": summary or {},
        "ts": __import__("datetime").datetime.now().isoformat(),
    }

    if _webhook_enabled():
        _send_webhook(payload)
    if _email_enabled():
        _send_email(payload)


def _send_webhook(payload: dict) -> None:
    url = os.getenv("NOTIFY_WEBHOOK_URL")
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        logger.info(f"Webhook notification sent for job {payload['job_id']}")
    except Exception as e:
        logger.error(f"Webhook notification failed for job {payload['job_id']}: {e}")


def _send_email(payload: dict) -> None:
    to = [e.strip() for e in os.getenv("NOTIFY_EMAIL_TO", "").split(",") if e.strip()]
    if not to:
        return
    from_addr = os.getenv("NOTIFY_EMAIL_FROM", to[0])
    subject = f"[mailcow-migrator] Job {payload['job_id']} {payload['event']}"

    body_lines = [
        f"Job #{payload['job_id']}",
        f"Event: {payload['event']}",
        f"Message: {payload['message']}",
        "",
    ]
    if payload.get("summary"):
        body_lines.append("Summary:")
        for key, value in payload["summary"].items():
            body_lines.append(f"  {key}: {value}")
        body_lines.append("")
    body = "\n".join(body_lines)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)

    try:
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as server:
            if os.getenv("SMTP_STARTTLS", "1").lower() in ("1", "true", "yes"):
                server.starttls()
            user = os.getenv("SMTP_USER")
            password = os.getenv("SMTP_PASSWORD")
            if user and password:
                server.login(user, password)
            server.sendmail(from_addr, to, msg.as_string())
        logger.info(f"Email notification sent for job {payload['job_id']}")
    except Exception as e:
        logger.error(f"Email notification failed for job {payload['job_id']}: {e}")
