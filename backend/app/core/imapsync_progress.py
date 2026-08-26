"""Parse imapsync's streaming progress output into job progress / ETA.

imapsync prints lines like:

  msg INBOX/423 {10010} copied to INBOX/139  2.02 msgs/s  1.647 MiB/s 125.501 MiB copied ETA: Wednesday 26 August 2026-08-26 13:29:30 +0000 UTC  330 s  668/832 msgs left

We extract the "done/left" message counts so the worker can drive a real
progress bar and estimate remaining time.
"""

import re
from typing import Optional

# e.g. "668/832 msgs left"  (done=668, left=832)
_MSGS_LEFT_RE = re.compile(r"\s(\d+)/(\d+)\s+msgs\s+left")

# e.g. "ETA: Wednesday 26 August 2026-08-26 13:29:30 +0000 UTC  330 s"
# (weekday, day, month, datetime, tz-offset, tz-name, then "<secs> s")
_ETA_RE = re.compile(r"ETA:\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)\s+s\s")

# Folder copy markers: "copying folder [INBOX]" / "folder [INBOX] selected N messages"
_FOLDER_SELECT_RE = re.compile(r"folder \[([^\]]+)\] selected (\d+) messages")

# Summary markers
_SUMMARY_DONE_RE = re.compile(r"^Total transferred messages, skipped messages, failures: .*?(\d+)/(\d+)")
_END_RE = re.compile(r"\b(folders done|Summary|Exiting with return value)\b", re.I)


class ProgressInfo:
    __slots__ = ("done", "total", "percent", "eta_seconds")

    def __init__(self, done: Optional[int] = None, total: Optional[int] = None,
                 eta_seconds: Optional[int] = None):
        self.done = done
        self.total = total
        self.eta_seconds = eta_seconds
        self.percent = round((done / total) * 100) if done is not None and total else None

    def as_dict(self) -> dict:
        return {
            "done": self.done,
            "total": self.total,
            "percent": self.percent,
            "eta_seconds": self.eta_seconds,
        }


def parse_progress_line(line: str) -> Optional[ProgressInfo]:
    """Return a ProgressInfo for a single imapsync output line, or None if the
    line carries no progress information."""
    m = _MSGS_LEFT_RE.search(line)
    if not m:
        return None
    left = int(m.group(2))
    done = int(m.group(1))
    eta = None
    em = _ETA_RE.search(line)
    if em:
        eta = int(em.group(1))
    return ProgressInfo(done=done, total=left, eta_seconds=eta)


def parse_folder_selection(line: str) -> Optional[dict]:
    """Detect folder selection lines and return {folder, total} or None."""
    m = _FOLDER_SELECT_RE.search(line)
    if m:
        return {"folder": m.group(1), "total": int(m.group(2))}
    return None
