from datetime import datetime
from plone import api
from rer.linkchecker.linkchecker import STATUS_CONNECTION_ERROR
from rer.linkchecker.linkchecker import STATUS_HTTPS_ONLY
from uuid import uuid4

import pytest
import requests


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}

    def close(self):
        pass


class BadChain:
    """A server whose certificate cannot be verified, e.g. because it omits
    its intermediate certificate: raises an SSLError on a verified request,
    answers normally on an unverified one."""

    def __init__(self, status):
        self.status = status


class FakeSession:
    """``statuses`` maps a url to the status to answer, to a BadChain, or to
    an exception instance to raise."""

    def __init__(self, statuses):
        self.statuses = statuses

    def head(self, url, verify=True, **kwargs):
        value = self.statuses[url]
        if isinstance(value, BadChain):
            if verify:
                raise requests.exceptions.SSLError(
                    "unable to get local issuer certificate"
                )
            return FakeResponse(value.status)
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value)

    get = head


@pytest.fixture
def linkchecker_content(portal):
    """Create the content the linkchecker tool checks links against."""
    with api.env.adopt_roles(["Manager"]):
        api.content.create(container=portal, type="Document", title="Foo document 2")

        document = api.content.create(
            container=portal, type="Document", title="Foo document"
        )
        document.blocks = {
            "xyz": {
                "@type": "testo_riquadro_immagine",
                "image_card_title": {"blocks": [{"text": "imagetitle"}]},
                "image_card_content": {"blocks": [{"text": "imagetext"}]},
                "text": {
                    "blocks": [
                        {
                            "urls": [
                                "https://httpstat.us/404",  # broken
                                f"/resolveuid/{uuid4()}",  # broken
                                f"/resolveuid/{document.UID()}",  # internal ok
                            ]
                        }
                    ]
                },
            },
        }
        document.blocks_layout = {"items": ["xyz"]}

        api.content.create(container=portal, type="Event", title="Foo event")

        link_524 = api.content.create(
            container=portal,
            type="Link",
            title="Foo link 524",
            remoteUrl="https://httpstat.us/524",
        )
        link_404 = api.content.create(
            container=portal,
            type="Link",
            title="Foo link 404",
            remoteUrl="https://httpstat.us/404",
        )

    return {
        "document": document,
        "link_524": link_524,
        "link_404": link_404,
        "tool": api.portal.get_tool("portal_linkchecker"),
    }


class TestLinkCheckerTool:
    def test_tool_exists(self, linkchecker_content):
        assert linkchecker_content["tool"]

    def test_clear(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        tool.clear()
        assert len(tool._external_links_status) == 0
        assert len(tool._outgoing_links) == 0
        assert tool._last_update is None

    def test_check_site(self, linkchecker_content):
        """Hits real external urls (httpstat.us) to exercise the full check."""
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        link_524 = linkchecker_content["link_524"]
        link_404 = linkchecker_content["link_404"]

        # a stale entry from a previous run must be pruned by check_site
        tool._outgoing_links["stale-uid"] = (datetime.now(), [])

        tool.check_site()
        assert tool._last_update is not None
        assert "stale-uid" not in tool._outgoing_links
        assert len(tool._outgoing_links) == 6
        assert len(tool._external_links_status) == 2

        broken_links = dict(tool.get_page_with_broken_links())
        assert len(broken_links) == 3
        assert link_524.UID() in broken_links
        assert link_404.UID() in broken_links
        assert document.UID() in broken_links
        assert len(broken_links[document.UID()]) == 2

    def test_any_2xx_status_is_not_broken(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        tool._outgoing_links[document.UID()] = (
            datetime.now(),
            [
                ("https://example.com/ok", 200),
                ("https://example.com/accepted", 202),
                ("https://example.com/broken", 404),
            ],
        )
        broken_links = dict(tool.get_page_with_broken_links())
        assert broken_links[document.UID()] == [("https://example.com/broken", 404)]
        rows = list(tool.get_rows(broken=True))
        assert len(rows) == 2  # header + the 404 row

    def test_deleted_content_is_skipped_in_report(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        # a UID that does not resolve to any content (deleted after the check)
        tool._outgoing_links["gone-uid"] = (
            datetime.now(),
            [("https://example.com/broken", 404)],
        )
        broken_links = dict(tool.get_page_with_broken_links())
        assert "gone-uid" not in broken_links
        rows = list(tool.get_rows(broken=True))
        assert len(rows) == 1  # header only, the gone content is skipped

    def test_bot_protected_links_are_not_broken(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        tool._outgoing_links[document.UID()] = (
            datetime.now(),
            [
                ("https://linkedin.com/x", 999),  # LinkedIn anti-bot
                ("https://foo.com/forbidden", 403),
                ("https://foo.com/throttled", 429),
                ("https://foo.com/broken", 404),
            ],
        )
        # only the real 404 is reported as broken
        broken_links = dict(tool.get_page_with_broken_links())
        assert broken_links[document.UID()] == [("https://foo.com/broken", 404)]
        # the blocked ones still show in the csv, with a dedicated description
        rows = list(tool.get_rows(broken=True))
        blocked = [row for row in rows if row[3] == 999]
        assert len(blocked) == 1
        assert "Blocked by bot protection" in blocked[0][4]

    def test_broken_http_link_working_on_https(self, linkchecker_content):
        tool = linkchecker_content["tool"]

        # http broken, https works -> flagged as "update to https"
        session = FakeSession({"http://foo.com/bar": 400, "https://foo.com/bar": 200})
        assert (
            tool._fetch_status(
                "http://foo.com/bar", timeout=1, headers={}, session=session
            )
            == STATUS_HTTPS_ONLY
        )

        # broken on both protocols -> keep the original status
        session = FakeSession({"http://foo.com/bar": 400, "https://foo.com/bar": 404})
        assert (
            tool._fetch_status(
                "http://foo.com/bar", timeout=1, headers={}, session=session
            )
            == 400
        )

    def test_request_headers_look_like_a_browser_navigation(self, linkchecker_content):
        """Two real-world false positives: www.edvance.it answers 404 to a
        request whose Accept is not html (what requests sends by default), and
        facebook.com answers 400 to one that claims to be a browser without the
        Sec-Fetch metadata of a real navigation."""
        headers = linkchecker_content["tool"].request_headers
        assert headers["Accept"].startswith("text/html")
        # but anything is still accepted, or pdf and image links would break
        assert "*/*" in headers["Accept"]
        assert headers["Sec-Fetch-Mode"] == "navigate"

    def test_certificates_are_not_verified(self, linkchecker_content):
        """The real-world case of www.sviluppoeconomico.gov.it: http answers
        404 and https works, but the server omits its intermediate certificate.
        BadChain answers only unverified requests, so these pass only as long
        as the checker keeps sending verify=False."""
        tool = linkchecker_content["tool"]

        # http broken, https reachable but with an unverifiable chain
        session = FakeSession({
            "http://foo.com/bar": 404,
            "https://foo.com/bar": BadChain(200),
        })
        assert (
            tool._fetch_status(
                "http://foo.com/bar", timeout=1, headers={}, session=session
            )
            == STATUS_HTTPS_ONLY
        )

        # a bad chain alone is no reason to report a link as broken
        session = FakeSession({"https://foo.com/bar": BadChain(200)})
        assert (
            tool._fetch_status(
                "https://foo.com/bar", timeout=1, headers={}, session=session
            )
            == 200
        )

        # a real tls failure is still a connection error
        session = FakeSession({
            "https://foo.com/bar": requests.exceptions.SSLError("handshake failed")
        })
        assert (
            tool._fetch_status(
                "https://foo.com/bar", timeout=1, headers={}, session=session
            )
            == STATUS_CONNECTION_ERROR
        )
