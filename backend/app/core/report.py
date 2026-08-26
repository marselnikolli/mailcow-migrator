"""Generate structured migration reports from a job's imapsync log.

Parses the stored per-job log (Redis) into a compact summary: messages
copied/skipped per folder, calendar/contacts counts, and job-level metadata.
"""

import re
from typing import List, Optional

_FOLDER_HEADER_RE = re.compile(r"Host1:\s+folder\s+\[([^\]]+)\]\s+selected\s+(\d+)\s+messages")
_FOLDER_DONE_RE = re.compile(r"folder\s+\[([^\]]+)\]\s+has\s+(\d+)\s+messages\s+in\s+total")
_COPIED_RE = re.compile(r"msg\s+\S+/\d+\s+\{\d+\}\s+copied\s+to\s+\S+/\d+\s+([\d.]+)\s+msgs/s")
_SKIPPED_RE = re.compile(r"msg\s+\S+/\d+\s+\{\d+\}\s+(?:already\s+transferred|skipped)\s+")
_CAL_SYNC_RE = re.compile(r"Uploaded (\d+) calendar items")
_CONTACT_SYNC_RE = re.compile(r"Uploaded (\d+) contacts")
_STARTED_RE = re.compile(r"Transfer started at (.+?)\s+PID")
_END_RE = re.compile(r"Exiting with return value (\d+)")


def build_report(job_id: int, log: str, job_meta: Optional[dict] = None) -> dict:
    """Parse a job's imapsync log into a structured report dict."""
    folders = {}
    copied_total = 0
    skipped_total = 0
    calendar_count = 0
    contacts_count = 0
    exit_code = None

    for line in log.splitlines():
        m = _FOLDER_HEADER_RE.search(line)
        if m:
            folder = m.group(1)
            folders.setdefault(folder, {"selected": 0, "copied": 0, "skipped": 0})
            folders[folder]["selected"] = int(m.group(2))
            continue

        m = _COPIED_RE.search(line)
        if m:
            folder = line.split("/", 1)[0].split(" ", 1)[-1]
            copied_total += 1
            folders.setdefault(folder, {"selected": 0, "copied": 0, "skipped": 0})
            folders[folder]["copied"] += 1
            continue

        if _SKIPPED_RE.search(line):
            skipped_total += 1
            continue

        m = _CAL_SYNC_RE.search(line)
        if m:
            calendar_count = int(m.group(1))
            continue

        m = _CONTACT_SYNC_RE.search(line)
        if m:
            contacts_count = int(m.group(1))
            continue

        m = _END_RE.search(line)
        if m:
            exit_code = int(m.group(1))

    report = {
        "job_id": job_id,
        "folders": folders,
        "summary": {
            "copied_messages": copied_total,
            "skipped_messages": skipped_total,
            "calendar_items": calendar_count,
            "contacts": contacts_count,
            "exit_code": exit_code,
            "success": exit_code == 0,
        },
    }
    if job_meta:
        report["job"] = job_meta
    return report


def report_to_csv(report: dict) -> str:
    """Render a report as CSV (rows: job, folder, selected, copied, skipped)."""
    rows = []
    for folder, stats in (report.get("folders") or {}).items():
        rows.append((
            report.get("job", {}).get("source_email", ""),
            report.get("job", {}).get("target_email", ""),
            folder,
            stats.get("selected", 0),
            stats.get("copied", 0),
            stats.get("skipped", 0),
        ))
    s = report.get("summary", {})
    rows.append((
        report.get("job", {}).get("source_email", ""),
        report.get("job", {}).get("target_email", ""),
        "__TOTAL__",
        s.get("copied_messages", 0),
        s.get("skipped_messages", 0),
        0,
    ))

    lines = ["source_email,target_email,folder,selected,copied,skipped"]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    return "\n".join(lines) + "\n"
