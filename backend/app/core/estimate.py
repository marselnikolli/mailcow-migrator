"""Source mailbox estimation: connect to the source via IMAP and report
folder names and message counts without transferring anything.

Used to power a dry-run estimate so admins can size the target before
committing to a real migration.
"""

import imaplib
import re
import ssl
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# IMAP LIST lines look like:  (\HasNoChildren \Archive) "/" "Archive"
_LIST_RE = re.compile(r'^\s*\(.*?\)\s+"?([^"]*)"?\s+"([^"]*)"\s*$')


def compute_since(maxage_days: Optional[int], since_date: Optional[str]) -> Optional[str]:
    """Resolve the job's date filters into the IMAP SINCE date (dd-Mon-yyyy).

    maxage_days counts back from today; since_date is an explicit YYYY-MM-DD.
    Mirrors the effect of imapsync's --maxage/--since so the estimate counts
    what would actually be migrated. Returns None when no date filter is set.
    """
    if since_date:
        try:
            d = datetime.strptime(since_date, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid since_date: {since_date!r} (expected YYYY-MM-DD)")
    elif maxage_days:
        d = date.today() - timedelta(days=int(maxage_days))
    else:
        return None
    return d.strftime("%d-%b-%Y")


class MailboxEstimator:
    def __init__(self, host: str, email: str, password: str, port: int = 993,
                 use_ssl: bool = True, timeout: int = 60):
        self.host = host
        self.email = email
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout

    def _connect(self):
        if self.use_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # matches imapsync's default
            conn = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ctx, timeout=self.timeout)
        else:
            conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
        conn.login(self.email, self.password)
        return conn

    @staticmethod
    def _parse_list_line(line: str) -> Optional[str]:
        """Extract the folder name from an IMAP LIST response line."""
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        m = _LIST_RE.match(line.strip())
        return m.group(2) if m else None

    @staticmethod
    def _count_search(conn, folder: str, since: str) -> int:
        """Count messages in a folder whose internal date is >= `since`, via
        IMAP SEARCH SINCE. This is what the estimate should report when the job
        has maxage_days/since_date filters, because it counts the messages
        imapsync would actually copy."""
        conn.select(folder, readonly=True)
        status, data = conn.search(None, "SINCE", f'"{since}"')
        if status != "OK":
            raise RuntimeError(f"SEARCH SINCE failed on {folder}: {data}")
        count = 0
        for chunk in data:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8", errors="replace")
            # imaplib returns a single space-separated sequence of message ids
            # (possibly across multiple lines for big folders).
            count += len([t for t in chunk.split() if t])
        return count

    def estimate(self, folders: Optional[str] = None, maxage_days: Optional[int] = None,
                 since_date: Optional[str] = None) -> dict:
        """Return a per-folder and total estimate for the source mailbox.

        Args:
            folders: optional comma-separated include list; None means all.
            maxage_days: only count messages from the last N days.
            since_date: only count messages whose internal date >= this date.

        When either date filter is set, per-folder counts come from a SEARCH
        SINCE (matching imapsync's --maxage/--since) rather than the raw EXISTS
        total, so date-filtered jobs are not overcounted.
        """
        include = [f.strip() for f in folders.split(",") if f.strip()] if folders else None
        since = compute_since(maxage_days, since_date)
        conn = self._connect()
        try:
            status, data = conn.list()
            if status != "OK":
                raise RuntimeError(f"LIST failed: {data}")

            folders_info = []
            total_messages = 0
            for line in data:
                name = self._parse_list_line(line)
                if not name:
                    continue
                if include and name not in include:
                    continue

                try:
                    if since:
                        exists = self._count_search(conn, name, since)
                    else:
                        conn.select(name, readonly=True)
                        # SELECT response contains:  * <n> EXISTS
                        exists = 0
                        for rline in conn.untagged_responses.get("EXISTS", []):
                            if isinstance(rline, bytes):
                                rline = rline.decode("utf-8", errors="replace")
                            try:
                                exists = int(rline.strip())
                            except ValueError:
                                pass
                        conn.untagged_responses.pop("EXISTS", None)
                except Exception as e:
                    logger.warning(f"Could not inspect folder {name}: {e}")
                    exists = 0

                folders_info.append({"folder": name, "messages": exists})
                total_messages += exists

            return {
                "source": self.email,
                "host": self.host,
                "folders": folders_info,
                "total_messages": total_messages,
                "filtered": since is not None,
            }
        finally:
            try:
                conn.logout()
            except Exception:
                pass
