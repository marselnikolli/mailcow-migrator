"""CalDAV/CardDAV migration for calendars and address books.

Source is expected to be a Zimbra/Carbonio server exposing collections at
  /dav/<user>/Calendar/  (CalDAV)
  /dav/<user>/Contacts/  (CardDAV)
Destination is expected to be Mailcow + SOGo exposing collections at
  /SOGo/dav/<user>/Calendar/
  /SOGo/dav/<user>/Contacts/

Items are read from the source with a REPORT and written to the destination
with PUT, keyed by the calendar object / vCard UID so re-runs overwrite the
same items instead of duplicating them.
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Callable, List, Optional
from urllib.parse import quote, urljoin

import requests

logger = logging.getLogger(__name__)

DAV_NS = "DAV:"
CALDAV_NS = "urn:ietf:params:xml:ns:caldav"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"

UID_RE = re.compile(r"(?im)^\s*UID[:;]\s*(\S+)")


class DavSyncError(Exception):
    """Raised when calendar/address book sync cannot proceed."""


def _tag(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def _text(element: Optional[ET.Element]) -> str:
    return element.text or "" if element is not None else ""


def _find(element: ET.Element, ns: str, name: str) -> Optional[ET.Element]:
    return element.find(_tag(ns, name))


def _findall(element: ET.Element, ns: str, name: str) -> List[ET.Element]:
    return element.findall(_tag(ns, name))


def _extract_uid(data: str, content_type: str) -> str:
    """Extract the UID from an iCalendar/vCard payload, lower-cased for use
    as a stable filename. Falls back to a sha1 of the payload so every item
    still gets a stable unique filename."""
    m = UID_RE.search(data)
    if m:
        return m.group(1)
    import hashlib
    return hashlib.sha1(data.encode("utf-8", errors="replace")).hexdigest()


class DavSyncer:
    def __init__(
        self,
        source_email: str,
        source_password: str,
        source_host: str,
        target_email: str,
        target_password: str,
        target_host: str,
        source_ssl: bool = True,
        target_ssl: bool = True,
        source_base: str = "/dav/",
        target_base: str = "/SOGo/dav/",
        timeout: int = 120,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.session = requests.Session()
        self.session.verify = False  # matches imapsync's default SSL_VERIFY_NONE
        requests.packages.urllib3.disable_warnings()

        src_scheme = "https" if source_ssl else "http"
        tgt_scheme = "https" if target_ssl else "http"
        user = quote(source_email, safe="")
        tuser = quote(target_email, safe="")

        self.source_calendar = urljoin(
            f"{src_scheme}://{source_host}{source_base}{user}/", "Calendar/"
        )
        self.source_contacts = urljoin(
            f"{src_scheme}://{source_host}{source_base}{user}/", "Contacts/"
        )
        self.target_calendar = urljoin(
            f"{tgt_scheme}://{target_host}{target_base}{tuser}/", "Calendar/"
        )
        self.target_contacts = urljoin(
            f"{tgt_scheme}://{target_host}{target_base}{tuser}/", "Contacts/"
        )

        self.source_auth = (source_email, source_password)
        self.target_auth = (target_email, target_password)
        self.timeout = timeout
        self.on_log = on_log

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)
        logger.info(message)

    # ---------------------------------------------------------------- helpers

    def _ensure_collection(self, url: str, auth: tuple) -> None:
        """Make sure the destination collection exists (MKCOL if missing)."""
        r = self.session.request("PROPFIND", url, auth=auth, timeout=self.timeout,
                                 headers={"Depth": "0"})
        if r.status_code in (200, 207):
            return
        if r.status_code == 404:
            mkcol = self.session.request("MKCOL", url, auth=auth, timeout=self.timeout)
            if mkcol.status_code not in (200, 201):
                raise DavSyncError(
                    f"Failed to create collection {url}: HTTP {mkcol.status_code} {mkcol.text[:200]}"
                )
            return
        raise DavSyncError(
            f"Failed to probe collection {url}: HTTP {r.status_code} {r.text[:200]}"
        )

    def _find_writable_collections(self, home_url: str, auth: tuple,
                                   wanted_type: str) -> List[str]:
        """PROPFIND the destination home (depth 1) and return the hrefs of the
        collections that are actual data collections of `wanted_type`
        (e.g. 'calendar' or 'addressbook'). SOGo keeps these under a home
        collection (e.g. /Calendar/personal/) and exposes read-only GAL /
        directory collections alongside them - those are filtered out."""
        r = self.session.request("PROPFIND", home_url, auth=auth, timeout=self.timeout,
                                 headers={"Depth": "1"})
        if r.status_code not in (200, 207):
            raise DavSyncError(
                f"PROPFIND {home_url} failed: HTTP {r.status_code} {r.text[:200]}"
            )
        from urllib.parse import urlsplit, urlunsplit
        base_parts = urlsplit(home_url)
        base_origin = urlunsplit((base_parts.scheme, base_parts.netloc, "", "", ""))
        found = []
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            raise DavSyncError(f"Failed to parse PROPFIND response from {home_url}: {e}")

        for response in _findall(root, DAV_NS, "response"):
            href = _text(_find(response, DAV_NS, "href"))
            if not href:
                continue
            types = set()
            for propstat in _findall(response, DAV_NS, "propstat"):
                status = _text(_find(propstat, DAV_NS, "status"))
                if "200" not in status:
                    continue
                prop = _find(propstat, DAV_NS, "prop")
                if prop is None:
                    continue
                resourcetype = _find(prop, DAV_NS, "resourcetype")
                if resourcetype is not None:
                    for child in resourcetype:
                        types.add(child.tag.split("}")[-1])
            # Exclude the home collection itself, GAL/directory collections and
            # principal resources; keep only real calendar/addressbook data.
            if (wanted_type in types
                    and "directory" not in types
                    and "principal" not in types):
                if href.startswith("http"):
                    found.append(href)
                elif href.startswith("/"):
                    found.append(base_origin + href)
                else:
                    found.append(base_origin + "/" + href.lstrip("/"))
        return found

    @staticmethod
    def _calendar_query_body() -> str:
        return f"""<?xml version="1.0"?>
<c:calendar-query xmlns:d="{DAV_NS}" xmlns:c="{CALDAV_NS}">
  <d:prop>
    <d:getetag/>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR"/>
  </c:filter>
</c:calendar-query>"""

    @staticmethod
    def _addressbook_query_body() -> str:
        return f"""<?xml version="1.0"?>
<c:addressbook-query xmlns:d="{DAV_NS}" xmlns:c="{CARDDAV_NS}">
  <d:prop>
    <d:getetag/>
    <c:address-data/>
  </d:prop>
  <c:filter>
    <c:prop-filter name="FN"/>
  </c:filter>
</c:addressbook-query>"""

    def _report_items(self, url: str, auth: tuple, body: str) -> List[dict]:
        """REPORT the collection and return [{href, etag, data}]."""
        r = self.session.request(
            "REPORT", url, auth=auth, timeout=self.timeout,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=body,
        )
        if r.status_code not in (200, 207):
            raise DavSyncError(f"REPORT {url} failed: HTTP {r.status_code} {r.text[:300]}")

        items = []
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError as e:
            raise DavSyncError(f"Failed to parse REPORT response from {url}: {e}")

        for response in _findall(root, DAV_NS, "response"):
            href = _text(_find(response, DAV_NS, "href"))
            data = None
            etag = None
            for propstat in _findall(response, DAV_NS, "propstat"):
                status = _text(_find(propstat, DAV_NS, "status"))
                if "200" not in status:
                    continue
                prop = _find(propstat, DAV_NS, "prop")
                if prop is None:
                    continue
                data = _text(_find(prop, CALDAV_NS, "calendar-data")) or \
                       _text(_find(prop, CARDDAV_NS, "address-data")) or data
                etag = _text(_find(prop, DAV_NS, "getetag")) or etag
            if href and data:
                items.append({"href": href, "etag": etag, "data": data})
        return items

    def _put_item(self, url: str, auth: tuple, filename: str, data: str,
                  content_type: str) -> None:
        r = self.session.put(
            urljoin(url, quote(filename)),
            auth=auth,
            timeout=self.timeout,
            headers={"Content-Type": content_type},
            data=data.encode("utf-8"),
        )
        if r.status_code not in (200, 201, 204):
            raise DavSyncError(
                f"PUT {filename} to {url} failed: HTTP {r.status_code} {r.text[:200]}"
            )

    # -------------------------------------------------------------- public API

    def _resolve_target(self, home_url: str, auth: tuple, wanted_type: str,
                        fallback_name: str) -> str:
        """Pick the destination collection to write into: the first writable
        'personal'-style collection under the home, or the home itself if the
        server doesn't nest collections."""
        self._ensure_collection(home_url, auth)
        collections = self._find_writable_collections(home_url, auth, wanted_type)
        if collections:
            return collections[0]
        # No nested data collections found - fall back to writing into the home.
        return home_url

    def sync_calendar(self) -> dict:
        """Migrate the calendar collection. Returns {total, uploaded}."""
        self._log(f"CalDAV source: {self.source_calendar}")
        target = self._resolve_target(self.target_calendar, self.target_auth, "calendar", "personal")
        self._log(f"CalDAV target: {target}")
        items = self._report_items(self.source_calendar, self.source_auth,
                                   self._calendar_query_body())
        self._log(f"Found {len(items)} calendar items on source")

        uploaded = 0
        for item in items:
            uid = _extract_uid(item["data"], "calendar")
            self._put_item(
                target, self.target_auth, f"{uid}.ics",
                item["data"], "text/calendar; charset=utf-8",
            )
            uploaded += 1
        if uploaded:
            self._log(f"Uploaded {uploaded} calendar items to {target}")
        return {"total": len(items), "uploaded": uploaded}

    def sync_contacts(self) -> dict:
        """Migrate the address book collection. Returns {total, uploaded}."""
        self._log(f"CardDAV source: {self.source_contacts}")
        target = self._resolve_target(self.target_contacts, self.target_auth, "addressbook", "personal")
        self._log(f"CardDAV target: {target}")
        items = self._report_items(self.source_contacts, self.source_auth,
                                   self._addressbook_query_body())
        self._log(f"Found {len(items)} contacts on source")

        uploaded = 0
        for item in items:
            uid = _extract_uid(item["data"], "vcard")
            self._put_item(
                target, self.target_auth, f"{uid}.vcf",
                item["data"], "text/vcard; charset=utf-8",
            )
            uploaded += 1
        if uploaded:
            self._log(f"Uploaded {uploaded} contacts to {target}")
        return {"total": len(items), "uploaded": uploaded}

    def run(self, sync_calendar: bool, sync_contacts: bool, dry_run: bool = False) -> dict:
        """Run the requested DAV syncs. In dry-run mode nothing is written to
        the destination, but sources are still probed and item counts logged."""
        results = {}
        if dry_run:
            if sync_calendar:
                self._log(f"[DRY RUN] CalDAV source: {self.source_calendar}")
                items = self._report_items(self.source_calendar, self.source_auth,
                                           self._calendar_query_body())
                self._log(f"[DRY RUN] Would upload {len(items)} calendar items")
                results["calendar"] = {"total": len(items), "uploaded": 0}
            if sync_contacts:
                self._log(f"[DRY RUN] CardDAV source: {self.source_contacts}")
                items = self._report_items(self.source_contacts, self.source_auth,
                                           self._addressbook_query_body())
                self._log(f"[DRY RUN] Would upload {len(items)} contacts")
                results["contacts"] = {"total": len(items), "uploaded": 0}
            return results

        if sync_calendar:
            results["calendar"] = self.sync_calendar()
        if sync_contacts:
            results["contacts"] = self.sync_contacts()
        return results
