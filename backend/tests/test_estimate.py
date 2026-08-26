"""Tests for the mailbox estimate module (parsing, folder counting)."""

from app.core.estimate import MailboxEstimator


def test_list_line_parsing():
    assert MailboxEstimator._parse_list_line('(\\HasNoChildren \\Archive) "/" "Archive"') == "Archive"
    assert MailboxEstimator._parse_list_line('(\\HasNoChildren) "/" "INBOX"') == "INBOX"
    assert MailboxEstimator._parse_list_line('(\\NoInferiors \\Junk) "/" "Junk"') == "Junk"
    assert MailboxEstimator._parse_list_line(b'(\\HasNoChildren) "/" "Sent"') == "Sent"
    assert MailboxEstimator._parse_list_line("garbage") is None


class FakeConn:
    def __init__(self, lines, exists_map):
        self._lines = lines
        self._exists_map = exists_map
        self.untagged_responses = {}
        self.logged_out = False

    def list(self):
        return "OK", self._lines

    def select(self, name, readonly=False):
        count = self._exists_map.get(name, 0)
        self.untagged_responses = {"EXISTS": [str(count).encode()]}
        return "OK", [f"{count} EXISTS".encode()]

    def login(self, *a):
        return "OK", []

    def logout(self):
        self.logged_out = True


def test_estimate_counts(monkeypatch):
    lines = [
        b'(\\HasNoChildren) "/" "INBOX"',
        b'(\\HasNoChildren) "/" "Sent"',
        b'(\\HasNoChildren) "/" "Archive"',
    ]
    exists = {"INBOX": 10, "Sent": 5, "Archive": 3}
    fake = FakeConn(lines, exists)
    estimator = MailboxEstimator(host="h", email="a@b.com", password="p")
    monkeypatch.setattr(estimator, "_connect", lambda: fake)

    result = estimator.estimate()
    assert result["total_messages"] == 18
    assert len(result["folders"]) == 3
    assert result["folders"][0]["messages"] == 10
    assert fake.logged_out


def test_estimate_with_folder_filter(monkeypatch):
    lines = [
        b'(\\HasNoChildren) "/" "INBOX"',
        b'(\\HasNoChildren) "/" "Sent"',
    ]
    exists = {"INBOX": 10, "Sent": 5}
    fake = FakeConn(lines, exists)
    estimator = MailboxEstimator(host="h", email="a@b.com", password="p")
    monkeypatch.setattr(estimator, "_connect", lambda: fake)

    result = estimator.estimate(folders="INBOX")
    assert len(result["folders"]) == 1
    assert result["folders"][0]["folder"] == "INBOX"
    assert result["total_messages"] == 10
