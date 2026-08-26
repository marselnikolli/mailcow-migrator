"""Source mailbox estimation: connect to the source via IMAP and report
folder names and message counts without transferring anything.

Used to power a dry-run estimate so admins can size the target before
committing to a real migration.
"""

import imaplib
import re
import ssl
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# IMAP LIST lines look like:  (\HasNoChildren \Archive) "/" "Archive"
_LIST_RE = re.compile(r'^\s*\(.*?\)\s+"?([^"]*)"?\s+"([^"]*)"\s*$')


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

    def estimate(self, folders: Optional[str] = None) -> dict:
        """Return a per-folder and total estimate for the source mailbox.

        Args:
            folders: optional comma-separated include list; None means all.
        """
        include = [f.strip() for f in folders.split(",") if f.strip()] if folders else None
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
            }
        finally:
            try:
                conn.logout()
            except Exception:
                pass
