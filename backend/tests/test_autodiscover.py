"""Tests for IMAP source autodiscovery."""

import app.core.autodiscover as autodiscover


def test_discover_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(autodiscover, "_tcp_connect", lambda h, p, timeout=3.0: False)
    host, port = autodiscover.discover_imap_host("user@example.com")
    assert host == "imap.gmail.com"
    assert port == 993


def test_discover_uses_first_responder(monkeypatch):
    # imap.example.com:993 responds, everything else fails.
    def fake_connect(host, port, timeout=3.0):
        return host == "imap.example.com" and port == 993

    monkeypatch.setattr(autodiscover, "_tcp_connect", fake_connect)
    monkeypatch.setattr(autodiscover, "_mx_hosts", lambda domain: [])

    host, port = autodiscover.discover_imap_host("user@example.com", default_host="fallback", default_port=993)
    assert host == "imap.example.com"
    assert port == 993


def test_discover_respects_mx(monkeypatch):
    def fake_connect(host, port, timeout=3.0):
        return host == "mailgw.example.com" and port == 143

    monkeypatch.setattr(autodiscover, "_tcp_connect", fake_connect)
    monkeypatch.setattr(autodiscover, "_mx_hosts", lambda domain: ["mailgw.example.com"])

    host, port = autodiscover.discover_imap_host("user@example.com", default_host="fallback", default_port=993)
    assert host == "mailgw.example.com"
    assert port == 143


def test_discover_no_domain():
    host, port = autodiscover.discover_imap_host("notanemail", default_host="d", default_port=1)
    assert host == "d"
    assert port == 1
