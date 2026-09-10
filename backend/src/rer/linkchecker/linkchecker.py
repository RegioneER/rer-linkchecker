from AccessControl import ClassSecurityInfo
from Acquisition import aq_base
from BTrees.OOBTree import OOBTree
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.client import responses
from OFS.SimpleItem import SimpleItem
from plone import api
from plone.dexterity.utils import iterSchemata
from plone.restapi.serializer.utils import RESOLVEUID_RE
from Products.CMFCore.utils import UniqueObject
from requests.adapters import HTTPAdapter
from urllib.parse import urlparse
from urllib3.exceptions import InsecureRequestWarning
from zExceptions import NotFound
from zope.interface import implementer
from zope.interface import Interface
from zope.schema import getFieldsInOrder

import json
import logging
import re
import requests
import threading
import transaction
import urllib3


logger = logging.getLogger(__name__)

# _fetch_status never verifies certificates (see its docstring): silence the
# warning urllib3 would otherwise emit for every single link it checks
urllib3.disable_warnings(InsecureRequestWarning)


class ILinkCheckerTool(Interface):
    """Link checker tool"""

    def clear():
        """Clear the status"""

    def check_site(ttl=3600 * 6, timeout=15, max_workers=10):
        """Check the site for links"""

    def check_content(content, ttl=3600 * 6, timeout=15):
        """Check the content for links"""


URL_REGEX = re.compile(
    r"((?:(?:https?://)(?:(?:www\.)?(?:[\da-z\.-]+)\.(?:[a-z]{2,6}))(?::[0-9]{1,4})?)(?:[^\"\s\\]*)?)"
)
RESOLVEUID_REGEX = re.compile(r"(resolve[Uu]id/[a-zA-Z0-9\-]+)")

DEFAULT_TTL = 3600 * 6
# generous timeout: some (slow) PA servers answer in ~4-6s even unloaded, and
# under concurrency they cross a tighter timeout and produce false -1 results
DEFAULT_TIMEOUT = 15
DEFAULT_WORKERS = 10
# how often (in handled items) to release memory / create a savepoint
CACHE_GC_EVERY = 500
# max simultaneous requests to the same host (avoid hammering / rate limiting)
DEFAULT_MAX_PER_HOST = 2
# statuses returned by bot-protection: the link usually works for a human but
# cannot be verified automatically (429 Too Many Requests, 403 Forbidden and
# LinkedIn's non-standard 999). Reported apart, not counted as broken.
BLOCKED_STATUSES = {403, 429, 999}
# fake statuses for links without a real http response. Negative so they can
# never collide with a real http status (e.g. LinkedIn really returns 999).
# the request timed out: the server is there but too slow (often recoverable
# by raising the timeout)
STATUS_TIMEOUT = -1
# the http:// link is broken but works over https://: update it in the content
STATUS_HTTPS_ONLY = -2
# connection error: host unreachable, DNS failure, connection refused/reset...
STATUS_CONNECTION_ERROR = -3

STATUS_DESCRIPTIONS = {
    STATUS_TIMEOUT: "Timeout (server too slow; try raising the timeout)",
    STATUS_HTTPS_ONLY: "Broken over http but works over https: update the link",
    STATUS_CONNECTION_ERROR: "Connection error (host unreachable, DNS failure, ...)",
}


def format_duration(seconds):
    """A duration in seconds, spelled out for a human reading a log.

    Sub-minute runs keep a decimal, since that is where the interesting
    difference is; longer ones are split into hours and minutes, because
    "took 4325.87 seconds" makes the reader do the division. The stored value
    keeps its full precision: this is only how it is printed.
    """
    if seconds is None:
        return "unknown"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}m {secs}s"


def log_progress(items, label, total, unit="items"):
    """Yield from ``items``, logging progress every 5%.

    ``total`` is passed in rather than measured: the interesting iterables
    here are generators (as_completed, a set being consumed) whose length is
    not known from the outside.
    """
    total = max(total, 1)
    next_update = 5
    for i, item in enumerate(items, start=1):
        percentage = min((i * 100) // total, 100)
        if percentage >= next_update:
            logger.info("### %s %d%% (%d/%d %s) ###", label, percentage, i, total, unit)
            next_update += 5
        yield item


@implementer(ILinkCheckerTool)
class LinkCheckerTool(UniqueObject, SimpleItem):
    """Tool to check links in the site"""

    id = "portal_linkchecker"
    meta_type = "Link Checker Tool"
    security = ClassSecurityInfo()

    def __init__(self):
        # link -> (last_update, status_code)
        self._external_links_status = OOBTree()
        # last update
        self._last_update = None
        # duration (in seconds) of the last full site check
        self._last_duration = None
        # UUID -> (last_update, [(link1, status1), (link2, status2), ...])
        self._outgoing_links = OOBTree()

    @property
    def user_agent(self):
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
        )

    @property
    def request_headers(self):
        """Headers sent when checking an external link.

        Accept is here because requests defaults it to ``*/*``, and some servers
        negotiate on it and answer 404 to a request that does not declare it
        accepts html, which would show up as a broken link. It keeps the
        ``*/*;q=0.8`` fallback a browser sends, so links to pdf or images are
        not rejected either.
        Sec-Fetch-Mode is here because claiming to be a browser through the user
        agent without the metadata a real navigation carries is enough for some
        servers to reject the request: facebook.com answers 400 to it, while it
        serves both a full browser and an honestly non-browser client.
        """
        return {
            "User-Agent": self.user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
            "Sec-Fetch-Mode": "navigate",
        }

    @property
    def portal_url(self):
        url = getattr(self, "_v_portal_url", None)
        if url is None:
            url = api.portal.get().absolute_url()
            self._v_portal_url = url
        return url

    def clear(self):
        """Clear the status"""
        self._external_links_status.clear()
        self._outgoing_links.clear()
        self._last_update = None
        self._last_duration = None

    def check_site(
        self, ttl=DEFAULT_TTL, timeout=DEFAULT_TIMEOUT, max_workers=DEFAULT_WORKERS
    ):
        """Check the site for links

        :param ttl: the time to live for the external links status
        :param timeout: per-request timeout (seconds) for external links
        :param max_workers: number of concurrent threads checking external links
        """
        start = datetime.now()
        logger.info("# Start checking site for links #")
        portal = api.portal.get()
        outgoing = self._crawl_outgoing_links(portal)
        statuses = self._check_links(
            outgoing, ttl=ttl, timeout=timeout, max_workers=max_workers
        )
        self._store_results(outgoing, statuses)

        self._last_update = datetime.now()
        self._last_duration = (self._last_update - start).total_seconds()
        logger.info(
            "# End checking site for links: took %s #",
            format_duration(self._last_duration),
        )

    def _crawl_outgoing_links(self, portal):
        """Phase 1: collect the outgoing links of every content (no network).

        :return: dict content UID -> list of links
        """
        catalog = api.portal.get_tool("portal_catalog")
        brains = catalog.unrestrictedSearchResults(
            path="/".join(portal.getPhysicalPath())
        )
        outgoing = {}
        for i, brain in enumerate(log_progress(brains, "CRAWL", len(brains)), start=1):
            try:
                obj = brain._unrestrictedGetObject()
            except (AttributeError, KeyError, NotFound):
                logger.warning("[Skipping] stale catalog entry %s", brain.getPath())
                continue
            logger.debug("[Crawling] %s", brain.getPath())
            outgoing[obj.UID()] = self._find_links(obj)
            if i % CACHE_GC_EVERY == 0:
                # keep the ZODB pickle cache under control on big sites
                portal._p_jar.cacheGC()

        # the site root (homepage blocks) may not be in the catalog
        try:
            portal_uid = portal.UID()
        except AttributeError:
            portal_uid = None
        if portal_uid and portal_uid not in outgoing:
            outgoing[portal_uid] = self._find_links(portal)
        return outgoing

    def _check_links(
        self,
        outgoing,
        ttl=DEFAULT_TTL,
        timeout=DEFAULT_TIMEOUT,
        max_workers=DEFAULT_WORKERS,
    ):
        """Phase 2: check every *unique* link the crawl found.

        A link shared by ten pages is checked once; external links go through
        the concurrent checker, internal ones resolve against the ZODB and are
        therefore done in this thread.

        :return: dict link -> status, covering every link in ``outgoing``
        """
        internal_links = set()
        external_links = set()
        for links in outgoing.values():
            for link in links:
                if self._is_internal(link):
                    internal_links.add(link)
                else:
                    external_links.add(link)

        logger.info(
            "# Checking %d unique external and %d unique internal links #",
            len(external_links),
            len(internal_links),
        )
        statuses = self._check_external_links(
            external_links, ttl=ttl, timeout=timeout, max_workers=max_workers
        )
        for link in log_progress(
            internal_links, "INTERNAL LINKS", len(internal_links), unit="links"
        ):
            statuses[link] = self._check_internal_link(link)
        return statuses

    def _store_results(self, outgoing, statuses):
        """Phase 3: store the per-content results, dropping the stale ones."""
        now = datetime.now()
        for count, (uuid, links) in enumerate(outgoing.items(), start=1):
            self._outgoing_links[uuid] = (
                now,
                [(link, statuses[link]) for link in links],
            )
            if count % CACHE_GC_EVERY == 0:
                transaction.savepoint(optimistic=True)

        # drop results of contents that no longer exist (deleted since the last
        # run), so the stored data mirrors the current site
        stale = [uuid for uuid in self._outgoing_links if uuid not in outgoing]
        for uuid in stale:
            del self._outgoing_links[uuid]
        if stale:
            logger.info("# Removed %d stale content(s) from results #", len(stale))

    def check_content(self, content, ttl=DEFAULT_TTL, timeout=DEFAULT_TIMEOUT):
        """Check the content for links

        :param content: the content to check
        :param ttl: the time to live for the external links status
        :param timeout: per-request timeout (seconds) for external links
        """
        uuid = content.UID()
        results = []
        for link in self._find_links(content):
            if self._is_internal(link):
                status = self._check_internal_link(link)
            else:
                status = self._check_external_link(link, ttl=ttl, timeout=timeout)
            results.append((link, status))
        self._outgoing_links[uuid] = (datetime.now(), results)

    @staticmethod
    def _is_ok(status):
        """A link is valid on any 2xx status: e.g. EUR-Lex answers
        202 Accepted for perfectly working documents."""
        return 200 <= status < 300

    @staticmethod
    def _is_blocked(status):
        """Bot-protection response: the link usually works for a human but
        cannot be verified automatically (e.g. LinkedIn 999, 403, 429)."""
        return status in BLOCKED_STATUSES

    @classmethod
    def _status_description(cls, status):
        """Human readable description of a link status"""
        if cls._is_blocked(status):
            return "Blocked by bot protection (works for a human, not verifiable)"
        return STATUS_DESCRIPTIONS.get(status) or responses.get(status, "")

    def get_page_with_broken_links(self):
        """
        :return: iterator with items as
                 (uid, [(link1, status1), link2, status2), ...])

        Bot-protected links (see _is_blocked) are not reported as broken, and
        contents deleted since the last check are skipped.
        """
        for uid, (_, links) in self._outgoing_links.items():
            if not api.content.find(UID=uid, unrestricted=True):
                # content deleted after the last check
                continue
            broken_links = [
                item
                for item in links
                if not self._is_ok(item[1]) and not self._is_blocked(item[1])
            ]
            if broken_links:
                yield (uid, broken_links)

    def get_broken_links(self):
        """Iterate the stored report, one dict per broken link.

        This is the flat view of the results and the single source every report
        is built from. Unlike get_page_with_broken_links, bot-protected links
        are included: they carry their own description, so a reader can tell
        "could not be verified" apart from "broken" and filter on it.
        Contents deleted since the last check are skipped.

        Deliberately unfiltered: walking the results costs one catalog lookup
        per content, so a caller that needs both the whole set (to count) and a
        subset (to display) walks once and filters with filter_links.

        The page an item belongs to is described with the plone.restapi field
        names (@id, @type, title, UID), so a client can treat it as any other
        content reference. The link's own fields are named apart from those:
        link_type, not type, and status_description, not description.
        """
        for uid, (last_update, links) in self._outgoing_links.items():
            broken = [item for item in links if not self._is_ok(item[1])]
            if not broken:
                continue
            brains = api.content.find(UID=uid, unrestricted=True)
            if not brains:
                # content deleted after the last check
                continue
            brain = brains[0]
            for link, status in broken:
                yield {
                    "@id": brain.getURL(),
                    "@type": brain.portal_type,
                    "title": brain.Title,
                    "UID": uid,
                    "link": link,
                    "link_type": (
                        "INTERNAL" if self._is_internal(link) else "EXTERNAL"
                    ),
                    "status": status,
                    "status_description": self._status_description(status),
                    "last_update": last_update,
                }

    @staticmethod
    def filter_links(items, status=None, link_type=None):
        """Filter get_broken_links items, the one place filtering happens.

        :param items: iterable of get_broken_links dicts
        :param status: keep only these statuses (iterable of int)
        :param link_type: keep only "INTERNAL" or "EXTERNAL"
        """
        wanted = set(status) if status else None
        for item in items:
            if wanted is not None and item["status"] not in wanted:
                continue
            if link_type is not None and item["link_type"] != link_type:
                continue
            yield item

    def get_rows(self, status=None, link_type=None):
        """The report as csv rows, header included.

        example usage:

            tool = api.portal.get_tool("portal_linkchecker")
            writer = csv.writer(open("broken_links.csv", "w"))
            for row in tool.get_rows():
                writer.writerow(row)
        """
        yield ["PAGE", "LINK", "TYPE", "STATUS", "DESCRIPTION"]
        items = self.filter_links(
            self.get_broken_links(), status=status, link_type=link_type
        )
        for item in items:
            yield [
                item["@id"],
                item["link"],
                item["link_type"],
                item["status"],
                item["status_description"],
            ]

    def _find_links(self, item):
        """Find links in the content

        Works on raw field values: blocks and richtext store internal links
        in the resolveuid/<uid> form, which is exactly what we want to check.
        """
        links = set()
        obj = aq_base(item)
        if not hasattr(obj, "portal_type"):
            return []
        for schemata in iterSchemata(obj):
            # the field itself is of no use here: values are read off the
            # object, raw, whatever the field type declares
            for name, _field in getFieldsInOrder(schemata):
                if name in ["blocks_layout"]:
                    continue
                value = getattr(obj, name, None)
                if not value:
                    continue
                # plone.app.textfield RichTextValue
                value = getattr(value, "raw", value)
                if isinstance(value, str):
                    text = value
                elif isinstance(value, dict):
                    try:
                        text = json.dumps(value)
                    except (TypeError, ValueError):
                        continue
                else:
                    continue
                links.update(re.findall(URL_REGEX, text))
                links.update(re.findall(RESOLVEUID_REGEX, text))
        return list(links)

    def _is_internal(self, link):
        """Check if the link is internal"""
        if link.startswith(self.portal_url):
            return True
        # an absolute url to another host is external; anything else is a
        # relative link (resolveuid/<uid>, /a/path), so it is ours
        return not link.startswith(("http://", "https://"))

    def _check_internal_link(self, link):
        """Check the internal link"""
        logger.debug("Checking internal link %s", link)
        link = link.replace(self.portal_url, "")
        # drop query string and fragment before resolving
        link = link.split("#")[0].split("?")[0]
        match = RESOLVEUID_RE.match(link)
        if match is not None:
            uid, _ = match.groups()
            if api.content.find(UID=uid, unrestricted=True):
                return 200
            else:
                return 404
        else:
            try:
                if api.content.get(path=link):
                    return 200
            except (NotFound, IndexError):
                return 404

        # TODO: redirection tool

        return 404

    def _check_external_links(
        self,
        links,
        ttl=DEFAULT_TTL,
        timeout=DEFAULT_TIMEOUT,
        max_workers=DEFAULT_WORKERS,
        max_per_host=DEFAULT_MAX_PER_HOST,
    ):
        """Check a set of unique external links, concurrently.

        Requests to the same host are throttled to ``max_per_host`` at a time
        so we don't hammer a single server (which would answer 503 / time out
        and produce false positives); different hosts still run in parallel.

        :return: dict link -> status
        """
        statuses, to_check = self._split_cached(links, ttl=ttl)
        if not to_check:
            # said out loud: nothing is fetched here, and a log that jumps
            # straight to the internal links looks like the external ones were
            # forgotten rather than answered out of the cache
            logger.info(
                "# Not checking the %d external links: their cached status is "
                "still fresh (ttl %ss, not expired yet). Use ttl=0 to force a "
                "recheck #",
                len(statuses),
                ttl,
            )
            return statuses

        logger.info(
            "# Checking %d external links (%d fresh from cache, ttl %ss) #",
            len(to_check),
            len(statuses),
            ttl,
        )
        fetched = self._fetch_statuses(
            to_check,
            timeout=timeout,
            max_workers=max_workers,
            max_per_host=max_per_host,
        )
        for link, status in log_progress(
            fetched, "EXTERNAL LINKS", len(to_check), unit="links"
        ):
            self._external_links_status[link] = (datetime.now(), status)
            statuses[link] = status
        return statuses

    def _split_cached(self, links, ttl=DEFAULT_TTL):
        """Tell the links whose cached status is still fresh from the rest.

        :return: (dict link -> cached status, list of links left to check)
        """
        now = datetime.now()
        statuses = {}
        to_check = []
        for link in links:
            cached = self._external_links_status.get(link)
            if cached and (now - cached[0]).total_seconds() < ttl:
                statuses[link] = cached[1]
            else:
                to_check.append(link)
        return statuses, to_check

    def _fetch_statuses(
        self,
        to_check,
        timeout=DEFAULT_TIMEOUT,
        max_workers=DEFAULT_WORKERS,
        max_per_host=DEFAULT_MAX_PER_HOST,
    ):
        """Yield (link, status) for each link in ``to_check``, over the network.

        With ``max_workers <= 1`` the checks run inline in the current thread
        (no ThreadPoolExecutor): handy to drop a pdb breakpoint, since a
        debugger cannot attach to worker threads. Nothing here touches the
        ZODB, precisely because it runs in threads.
        """
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=max_workers, pool_maxsize=max_workers)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        headers = self.request_headers
        # one semaphore per host, built upfront to avoid races between threads
        semaphores = {
            host: threading.Semaphore(max_per_host)
            for host in {self._host_of(link) for link in to_check}
        }

        def worker(link):
            with semaphores[self._host_of(link)]:
                logger.debug("Checking external link %s", link)
                status = self._fetch_status(
                    link, timeout=timeout, headers=headers, session=session
                )
                logger.debug("Checked external link %s -> %s", link, status)
                return status

        if max_workers <= 1:
            for link in to_check:
                yield link, worker(link)
            return
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(worker, link): link for link in to_check}
            for future in as_completed(futures):
                yield futures[future], future.result()

    @staticmethod
    def _host_of(link):
        """Lowercased host of a link, used to group/throttle requests"""
        try:
            return urlparse(link).netloc.lower()
        except ValueError:
            return ""

    def _check_external_link(self, link, ttl=DEFAULT_TTL, timeout=DEFAULT_TIMEOUT):
        """Check a single external link, honoring the cached status"""
        logger.debug("Checking external link %s", link)
        cached = self._external_links_status.get(link)
        if cached:
            last_update, status = cached
            if (datetime.now() - last_update).total_seconds() < ttl:
                return status
        headers = self.request_headers
        status = self._fetch_status(link, timeout=timeout, headers=headers)
        self._external_links_status[link] = (datetime.now(), status)
        return status

    @staticmethod
    def _fetch_status(link, timeout, headers, session=None):
        """Fetch the status of an external link.

        HEAD avoids downloading the body; some servers mishandle HEAD, so
        statuses >= 400 are double-checked with a streaming GET.
        No retries: a transient failure (timeout, 429, 503) is reported as-is.
        It may be a false positive, but retrying every failing link would slow
        a full-site check down too much.
        A broken http:// link that works over https is reported as
        STATUS_HTTPS_ONLY: browsers silently upgrade to https, so the link
        appears to work but should be updated in the content.
        Certificates are never verified (verify=False): we only care whether
        the resource is reachable, and plenty of otherwise working servers omit
        their intermediate certificate, which browsers fetch themselves but
        requests/certifi does not, so verifying would report them as broken.
        Called from worker threads: must not touch the ZODB.
        """
        if session is None:
            session = requests.Session()

        def fetch(url):
            try:
                res = session.head(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True,
                    verify=False,
                )
                status = res.status_code
                if status >= 400:
                    res = session.get(
                        url,
                        headers=headers,
                        timeout=timeout,
                        stream=True,
                        verify=False,
                    )
                    status = res.status_code
                    res.close()
                return status
            except requests.exceptions.Timeout:
                return STATUS_TIMEOUT
            except requests.exceptions.RequestException:
                return STATUS_CONNECTION_ERROR

        status = fetch(link)
        if not LinkCheckerTool._is_ok(status) and link.startswith("http://"):
            https_link = link.replace("http://", "https://", 1)
            if LinkCheckerTool._is_ok(fetch(https_link)):
                return STATUS_HTTPS_ONLY
        return status
