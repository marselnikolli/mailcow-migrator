import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def validate_public_url(url: str, field_name: str = "url") -> None:
    """Reject URLs that would let a caller make the server issue requests to
    itself or to internal/private network ranges (SSRF). Only http/https with
    a hostname that resolves exclusively to public addresses is allowed.

    This is best-effort (DNS can change between this check and the actual
    request), but it closes off the straightforward attack of pointing a
    job's mailcow_url at localhost, RFC1918 ranges, or the cloud metadata
    endpoint.
    """
    if not url:
        return

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"{field_name} must use http or https")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError(f"{field_name} is missing a hostname")

    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        raise UnsafeUrlError(f"{field_name} hostname could not be resolved")

    for addr in addrs:
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeUrlError(
                f"{field_name} resolves to a non-public address ({addr}), which is not allowed"
            )
