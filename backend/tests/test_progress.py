"""Tests for the imapsync progress parser."""

from app.core.imapsync_progress import parse_folder_selection, parse_progress_line


def test_parse_progress_line():
    line = ("msg INBOX/423 {10010} copied to INBOX/139  2.02 msgs/s  1.647 MiB/s "
            "125.501 MiB copied ETA: Wednesday 26 August 2026-08-26 13:29:30 +0000 UTC  "
            "330 s  668/832 msgs left")
    info = parse_progress_line(line)
    assert info is not None
    assert info.done == 668
    assert info.total == 832
    assert info.eta_seconds == 330
    assert info.percent == 80


def test_parse_progress_line_ignores_non_progress():
    assert parse_progress_line("Host1: connecting and login on host1 ...") is None
    assert parse_progress_line("") is None


def test_parse_progress_zero_total():
    info = parse_progress_line("msg A/1 {} 0/0 msgs left")
    assert info is not None
    assert info.percent is None  # no division by zero


def test_parse_folder_selection():
    d = parse_folder_selection("Host2: folder [INBOX] selected 744 messages, duplicates 0")
    assert d == {"folder": "INBOX", "total": 744}


def test_parse_folder_selection_none():
    assert parse_folder_selection("msg INBOX/1 {100} copied") is None
