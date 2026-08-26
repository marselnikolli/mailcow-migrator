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
