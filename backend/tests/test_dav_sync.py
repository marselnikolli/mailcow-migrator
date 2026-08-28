"""Tests for the CalDAV/CardDAV sync module."""

import xml.etree.ElementTree as ET

from app.core.dav_sync import DavSyncError, DavSyncer, _extract_uid

CAL_QUERY_RESPONSE = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:response>
    <D:href>/dav/u/Calendar/ev1.ics</D:href>
    <D:propstat>
      <D:status>HTTP/1.1 200 OK</D:status>
      <D:prop>
        <D:getetag>"abc"</D:getetag>
        <C:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-1
SUMMARY:Test
END:VEVENT
END:VCALENDAR</C:calendar-data>
      </D:prop>
    </D:propstat>
  </D:response>
</D:multistatus>"""

PROPFIND_RESPONSE = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/SOGo/dav/u/Calendar/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/SOGo/dav/u/Calendar/personal/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/><D:calendar xmlns="urn:ietf:params:xml:ns:caldav"/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/SOGo/dav/u/Contacts/dcfa.al/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/><D:addressbook xmlns="urn:ietf:params:xml:ns:carddav"/><D:directory/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
</D:multistatus>"""


def make_syncer():
    return DavSyncer(
        source_email="user@example.com",
        source_password="sp",
        source_host="src.example.com",
        target_email="user@example.com",
        target_password="tp",
        target_host="dst.example.com",
    )


def test_extract_uid_ics():
    data = "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:abc-123\nEND:VEVENT\nEND:VCALENDAR"
    assert _extract_uid(data, "calendar") == "abc-123"


def test_extract_uid_vcard():
    data = "BEGIN:VCARD\nUID:abc-456\nFN:Test\nEND:VCARD"
    assert _extract_uid(data, "vcard") == "abc-456"


def test_extract_uid_fallback_sha1():
    data = "BEGIN:VCARD\nFN:No UID\nEND:VCARD"
    uid = _extract_uid(data, "vcard")
    assert len(uid) == 40  # sha1 hex
    assert _extract_uid(data, "vcard") == uid  # stable


def test_report_items_parses_multistatus(monkeypatch):
    syncer = make_syncer()

    class FakeResp:
        status_code = 207
        content = CAL_QUERY_RESPONSE.encode()

    fake = FakeResp()
    monkeypatch.setattr(syncer.session, "request", lambda *a, **k: fake)

    items = syncer._report_items(
        syncer.source_calendar, syncer.source_auth, syncer._calendar_query_body()
    )
    assert len(items) == 1
    assert items[0]["href"] == "/dav/u/Calendar/ev1.ics"
    assert "UID:uid-1" in items[0]["data"]
    assert items[0]["etag"] == '"abc"'


def test_report_items_raises_on_error(monkeypatch):
    syncer = make_syncer()

    class FakeResp:
        status_code = 500
        text = "boom"

    monkeypatch.setattr(syncer.session, "request", lambda *a, **k: FakeResp())
    try:
        syncer._report_items(syncer.source_calendar, syncer.source_auth, "<x/>")
        assert False, "expected DavSyncError"
    except DavSyncError:
        pass


def test_find_writable_collections_filters_gal(monkeypatch):
    syncer = make_syncer()

    class FakeResp:
        status_code = 207
        content = PROPFIND_RESPONSE.encode()

    monkeypatch.setattr(syncer.session, "request", lambda *a, **k: FakeResp())

    calendars = syncer._find_writable_collections(
        syncer.target_calendar, syncer.target_auth, "calendar"
    )
    # Only the personal calendar (directory GAL + home excluded).
    assert len(calendars) == 1
    assert calendars[0].endswith("/Calendar/personal/")

    addressbooks = syncer._find_writable_collections(
        syncer.target_contacts, syncer.target_auth, "addressbook"
    )
    # GAL directory excluded; personal not present in fixture, so empty.
    assert addressbooks == []


def test_estimate_counts_without_writing(monkeypatch):
    syncer = make_syncer()

    class FakeResp:
        status_code = 207
        content = CAL_QUERY_RESPONSE.encode()

    # Calendar query returns 1 item; contacts/tasks collections raise.
    def fake_request(method, url, **kwargs):
        if method == "REPORT" and "Calendar" in url:
            return FakeResp()
        raise DavSyncError("no collection")

    monkeypatch.setattr(syncer.session, "request", fake_request)
    result = syncer.estimate(sync_calendar=True, sync_contacts=True, sync_tasks=True)
    assert result == {"calendar": 1, "contacts": 0, "tasks": 0}


def test_estimate_does_not_network_when_not_requested(monkeypatch):
    syncer = make_syncer()

    def never(*a, **k):
        raise AssertionError("estimate() must not touch the network when no sync flags are set")

    monkeypatch.setattr(syncer.session, "request", never)
    assert syncer.estimate() == {"calendar": 0, "contacts": 0, "tasks": 0}


SOURCE_HOME_PROPFIND_RESPONSE = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:response>
    <D:href>/dav/user%40example.com/Contacts/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/dav/user%40example.com/Emailed Contacts/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/><C:addressbook/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
  <D:response>
    <D:href>/dav/user%40example.com/Calendar/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
</D:multistatus>"""


def make_vcard_report_response(uid: str) -> str:
    return f"""<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:response>
    <D:href>/dav/u/x/{uid}.vcf</D:href>
    <D:propstat>
      <D:status>HTTP/1.1 200 OK</D:status>
      <D:prop>
        <D:getetag>"etag-{uid}"</D:getetag>
        <C:address-data>BEGIN:VCARD
UID:{uid}
FN:Test {uid}
END:VCARD</C:address-data>
      </D:prop>
    </D:propstat>
  </D:response>
</D:multistatus>"""


def test_sync_contacts_discovers_all_source_addressbooks(monkeypatch):
    """Regression test: Zimbra/Carbonio keeps 'Emailed Contacts' (folder id 13)
    as a sibling collection next to 'Contacts' (folder id 7), not inside it.
    sync_contacts() must find and migrate both, not just the hardcoded
    '/Contacts/' collection."""
    syncer = make_syncer()
    put_calls = []

    class PropfindHomeResp:
        status_code = 207
        content = SOURCE_HOME_PROPFIND_RESPONSE.encode()

    TARGET_HOME_PROPFIND_EMPTY = """<?xml version="1.0"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/SOGo/dav/user%40example.com/Contacts/</D:href>
    <D:propstat><D:status>HTTP/1.1 200 OK</D:status><D:prop>
      <D:resourcetype><D:collection/></D:resourcetype>
    </D:prop></D:propstat>
  </D:response>
</D:multistatus>"""

    class PropfindTargetResp:
        status_code = 207
        content = TARGET_HOME_PROPFIND_EMPTY.encode()

    def fake_request(method, url, **kwargs):
        if method == "PROPFIND" and url == syncer.source_home:
            return PropfindHomeResp()
        if method == "PROPFIND" and url == syncer.target_contacts:
            return PropfindTargetResp()
        if method == "REPORT" and "Contacts" in url and "Emailed" not in url:
            class Resp:
                status_code = 207
                content = make_vcard_report_response("uid-contacts-1").encode()
            return Resp()
        if method == "REPORT" and "Emailed Contacts" in url:
            class Resp:
                status_code = 207
                content = make_vcard_report_response("uid-emailed-1").encode()
            return Resp()
        raise AssertionError(f"unexpected request {method} {url}")

    def fake_put(url, **kwargs):
        put_calls.append(url)

        class PutResp:
            status_code = 201
        return PutResp()

    monkeypatch.setattr(syncer.session, "request", fake_request)
    monkeypatch.setattr(syncer.session, "put", fake_put)

    result = syncer.sync_contacts()

    assert result == {"total": 2, "uploaded": 2}
    assert any("uid-contacts-1" in c for c in put_calls)
    assert any("uid-emailed-1" in c for c in put_calls)
