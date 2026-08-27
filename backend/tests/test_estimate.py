"""Tests for the mailbox estimate module (parsing, folder counting)."""

from datetime import date, timedelta

from app.core.estimate import MailboxEstimator, compute_since


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
    assert result["filtered"] is False


class FakeSearchConn:
    """Fake IMAP connection that implements SELECT + SEARCH SINCE."""

    def __init__(self, lines, search_map):
        self._lines = lines
        self._search_map = search_map  # folder name -> space-separated ids
        self._selected = None
        self.logged_out = False

    def list(self):
        return "OK", self._lines

    def select(self, name, readonly=False):
        self._selected = name
        return "OK", [b"0 EXISTS"]

    def search(self, *args):
        ids = self._search_map.get(self._selected, "")
        return "OK", [ids.encode()]

    def login(self, *a):
        return "OK", []

    def logout(self):
        self.logged_out = True


def test_estimate_with_date_filter_uses_search(monkeypatch):
    lines = [b'() "/" "INBOX"', b'() "/" "Sent"', b'() "/" "Archive"']
    search_map = {"INBOX": "1 2 3 4", "Sent": "5 6", "Archive": ""}
    fake = FakeSearchConn(lines, search_map)
    estimator = MailboxEstimator(host="h", email="a@b.com", password="p")
    monkeypatch.setattr(estimator, "_connect", lambda: fake)

    result = estimator.estimate(maxage_days=30)
    assert result["total_messages"] == 6
    assert result["filtered"] is True
    assert fake.logged_out


def test_estimate_with_since_date_and_folder_filter(monkeypatch):
    lines = [b'() "/" "INBOX"', b'() "/" "Sent"']
    search_map = {"INBOX": "7 8 9"}
    fake = FakeSearchConn(lines, search_map)
    estimator = MailboxEstimator(host="h", email="a@b.com", password="p")
    monkeypatch.setattr(estimator, "_connect", lambda: fake)

    result = estimator.estimate(folders="INBOX", since_date="2024-01-15")
    assert result["total_messages"] == 3
    assert result["filtered"] is True


def test_compute_since():
    assert compute_since(None, None) is None
    expected = (date.today() - timedelta(days=30)).strftime("%d-%b-%Y")
    assert compute_since(30, None) == expected
    assert compute_since(None, "2024-01-15") == "15-Jan-2024"
    try:
        compute_since(None, "not-a-date")
        assert False, "expected ValueError"
    except ValueError:
        pass
