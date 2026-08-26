"""Best-effort IMAP source autodiscovery.

Given a source email, try the well-known IMAP hostnames for its domain plus
SRV records and return the first that answers a TCP connect on a common IMAP
port (993/143). Falls back to the caller-provided default when nothing
responds, so the tool keeps working for servers that don't advertise
themselves.
"""

import logging
import socket
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

IMAP_PORTS = [993, 143]


def _tcp_connect(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _mx_hosts(domain: str) -> list:
    """Return hostnames from the domain's MX records (best effort)."""
    try:
        import dns.resolver  # only used if dnspython is installed
        try:
            answers = dns.resolver.resolve(domain, "MX", lifetime=3)
            return [str(r.exchange).rstrip(".") for r in answers]
        except Exception:
            return []
    except ImportError:
        return []


def discover_imap_host(email: str, default_host: str = "imap.gmail.com",
                       default_port: int = 993) -> Tuple[str, int]:
    """Return (host, port) for the source email's IMAP server.

    Candidates are probed in order: SRV _imaps._tcp.<domain>, then common
    hostnames, then MX hosts. First responder wins.
    """
    domain = (email or "").split("@")[-1].strip().lower()
    if not domain:
        return default_host, default_port

    candidates = []

    # SRV record: _imaps._tcp.<domain>
    try:
        import dns.resolver
        try:
            answers = dns.resolver.resolve(f"_imaps._tcp.{domain}", "SRV", lifetime=3)
            for r in answers:
                target = str(r.target).rstrip(".")
                candidates.append((target, r.port or 993))
        except Exception:
            pass
    except ImportError:
        pass

    # Common hostnames
    for prefix in ("imap", "mail", "imapmail", "smtp"):
        candidates.append((f"{prefix}.{domain}", 993))
        candidates.append((f"{prefix}.{domain}", 143))

    # MX hosts
    for mx in _mx_hosts(domain):
        candidates.append((mx, 993))
        candidates.append((mx, 143))

    for host, port in candidates:
        if _tcp_connect(host, port):
            logger.info(f"Autodiscovered IMAP server {host}:{port} for {email}")
            return host, port

    return default_host, default_port
