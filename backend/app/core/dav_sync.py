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


class PauseRequested(DavSyncError):
    """Raised internally when a cooperative pause is requested mid-sync.

    Distinct from a hard failure: the worker catches this and marks the job
    PAUSED (resumable) instead of FAILED."""


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
        should_pause: Optional[Callable[[], bool]] = None,
    ):
        self.session = requests.Session()
        self.session.verify = False  # matches imapsync's default SSL_VERIFY_NONE
        requests.packages.urllib3.disable_warnings()

        src_scheme = "https" if source_ssl else "http"
        tgt_scheme = "https" if target_ssl else "http"
        user = quote(source_email, safe="")
        tuser = quote(target_email, safe="")

        self.source_home = f"{src_scheme}://{source_host}{source_base}{user}/"
        self.source_calendar = urljoin(
            f"{src_scheme}://{source_host}{source_base}{user}/", "Calendar/"
        )
        self.source_contacts = urljoin(
            f"{src_scheme}://{source_host}{source_base}{user}/", "Contacts/"
        )
        self.source_tasks = urljoin(
            f"{src_scheme}://{source_host}{source_base}{user}/", "Tasks/"
        )
        self.target_calendar = urljoin(
            f"{tgt_scheme}://{target_host}{target_base}{tuser}/", "Calendar/"
        )
        self.target_contacts = urljoin(
            f"{tgt_scheme}://{target_host}{target_base}{tuser}/", "Contacts/"
        )
        self.target_tasks = urljoin(
            f"{tgt_scheme}://{target_host}{target_base}{tuser}/", "Tasks/"
        )

        self.source_auth = (source_email, source_password)
        self.target_auth = (target_email, target_password)
        self.timeout = timeout
        self.on_log = on_log
        self.should_pause = should_pause

    def _log(self, message: str) -> None:
        if self.on_log:
            self.on_log(message)
        logger.info(message)

    def _check_pause(self) -> None:
        """Honor a cooperative pause between items. Each PUT is atomic and
        idempotent (keyed by UID), so stopping here is always safe."""
        if self.should_pause and self.should_pause():
            raise PauseRequested()

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

    def _source_addressbook_urls(self) -> List[str]:
        """Discover every address book collection under the source user's DAV
        home, not just the one literally named 'Contacts'.

        Zimbra/Carbonio exposes each contacts folder as its own sibling DAV
        collection under the user home - e.g. the built-in 'Emailed Contacts'
        folder (autocomplete addresses, typically folder id 13) lives next to
        'Contacts' (folder id 7), not inside it. Syncing only the hardcoded
        Contacts URL silently misses those. Falls back to the hardcoded
        Contacts URL if the home can't be enumerated (e.g. older servers)."""
        try:
            addressbooks = self._find_writable_collections(
                self.source_home, self.source_auth, "addressbook"
            )
        except DavSyncError as e:
            self._log(f"Could not enumerate address books under {self.source_home}: {e}")
            addressbooks = []
        if not addressbooks:
            addressbooks = [self.source_contacts]
        return addressbooks

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
            self._check_pause()
            uid = _extract_uid(item["data"], "calendar")
            self._put_item(
                target, self.target_auth, f"{uid}.ics",
                item["data"], "text/calendar; charset=utf-8",
            )
            uploaded += 1
        if uploaded:
            self._log(f"Uploaded {uploaded} calendar items to {target}")
        return {"total": len(items), "uploaded": uploaded}

    def sync_tasks(self) -> dict:
        """Migrate the VTODO (tasks) collection if the source exposes one.

        Some servers (e.g. SOGo) expose tasks under a separate collection;
        Zimbra typically folds VTODOs into the calendar. Probes the source and
        gracefully no-ops when there is no tasks collection."""
        self._log(f"CalDAV tasks source: {self.source_tasks}")
        try:
            target = self._resolve_target(self.target_tasks, self.target_auth, "calendar", "personal")
        except DavSyncError:
            self._log("No writable tasks collection on target - skipping tasks sync")
            return {"total": 0, "uploaded": 0}

        try:
            items = self._report_items(self.source_tasks, self.source_auth,
                                       self._calendar_query_body())
        except DavSyncError:
            self._log("No tasks collection on source - skipping tasks sync")
            return {"total": 0, "uploaded": 0}

        self._log(f"Found {len(items)} task items on source")
        uploaded = 0
        for item in items:
            self._check_pause()
            uid = _extract_uid(item["data"], "calendar")
            self._put_item(
                target, self.target_auth, f"{uid}.ics",
                item["data"], "text/calendar; charset=utf-8",
            )
            uploaded += 1
        if uploaded:
            self._log(f"Uploaded {uploaded} task items to {target}")
        return {"total": len(items), "uploaded": uploaded}

    def sync_contacts(self) -> dict:
        """Migrate every address book collection on the source (not just the
        one named 'Contacts'). Returns {total, uploaded}."""
        target = self._resolve_target(self.target_contacts, self.target_auth, "addressbook", "personal")
        self._log(f"CardDAV target: {target}")

        addressbooks = self._source_addressbook_urls()
        self._log(f"CardDAV source address books: {', '.join(addressbooks)}")

        items = []
        for source in addressbooks:
            try:
                found = self._report_items(source, self.source_auth,
                                           self._addressbook_query_body())
            except DavSyncError as e:
                self._log(f"Skipping address book {source}: {e}")
                continue
            self._log(f"Found {len(found)} contacts in {source}")
            items.extend(found)

        uploaded = 0
        for item in items:
            self._check_pause()
            uid = _extract_uid(item["data"], "vcard")
            self._put_item(
                target, self.target_auth, f"{uid}.vcf",
                item["data"], "text/vcard; charset=utf-8",
            )
            uploaded += 1
        if uploaded:
            self._log(f"Uploaded {uploaded} contacts to {target}")
        return {"total": len(items), "uploaded": uploaded}

    def estimate(self, sync_calendar: bool = False, sync_contacts: bool = False,
                 sync_tasks: bool = False) -> dict:
        """Count items on the source collections without writing anything.

        The same REPORT probes dry-run uses, minus any transfer. Missing
        collections are counted as 0 rather than raised, so a scan can't fail
        the whole job just because a server doesn't expose a tasks collection.
        Returns {"calendar": int, "contacts": int, "tasks": int}."""
        results = {}
        if sync_calendar:
            try:
                items = self._report_items(self.source_calendar, self.source_auth,
                                           self._calendar_query_body())
            except DavSyncError as e:
                self._log(f"Calendar estimate failed: {e}")
                items = []
            results["calendar"] = len(items)
        else:
            results["calendar"] = 0
        if sync_tasks:
            try:
                items = self._report_items(self.source_tasks, self.source_auth,
                                           self._calendar_query_body())
            except DavSyncError:
                items = []
            results["tasks"] = len(items)
        else:
            results["tasks"] = 0
        if sync_contacts:
            total = 0
            for source in self._source_addressbook_urls():
                try:
                    items = self._report_items(source, self.source_auth,
                                               self._addressbook_query_body())
                except DavSyncError as e:
                    self._log(f"Contacts estimate failed for {source}: {e}")
                    items = []
                total += len(items)
            results["contacts"] = total
        else:
            results["contacts"] = 0
        return results

    def run(self, sync_calendar: bool, sync_contacts: bool, sync_tasks: bool = False,
            dry_run: bool = False) -> dict:
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
            if sync_tasks:
                self._log(f"[DRY RUN] CalDAV tasks source: {self.source_tasks}")
                try:
                    items = self._report_items(self.source_tasks, self.source_auth,
                                               self._calendar_query_body())
                    self._log(f"[DRY RUN] Would upload {len(items)} task items")
                except DavSyncError:
                    items = []
                    self._log("[DRY RUN] No tasks collection on source")
                results["tasks"] = {"total": len(items), "uploaded": 0}
            if sync_contacts:
                addressbooks = self._source_addressbook_urls()
                self._log(f"[DRY RUN] CardDAV source address books: {', '.join(addressbooks)}")
                total = 0
                for source in addressbooks:
                    try:
                        items = self._report_items(source, self.source_auth,
                                                   self._addressbook_query_body())
                    except DavSyncError as e:
                        self._log(f"[DRY RUN] Skipping address book {source}: {e}")
                        items = []
                    total += len(items)
                self._log(f"[DRY RUN] Would upload {total} contacts")
                results["contacts"] = {"total": total, "uploaded": 0}
            return results

        if sync_calendar:
            results["calendar"] = self.sync_calendar()
        if sync_tasks:
            results["tasks"] = self.sync_tasks()
        if sync_contacts:
            results["contacts"] = self.sync_contacts()
        return results
