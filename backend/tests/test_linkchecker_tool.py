from datetime import datetime
from plone import api
from rer.linkchecker.linkchecker import BLACKLIST_ENV
from rer.linkchecker.linkchecker import blacklisted_domains
from rer.linkchecker.linkchecker import extract_links
from rer.linkchecker.linkchecker import HostBreaker
from rer.linkchecker.linkchecker import is_blacklisted
from rer.linkchecker.linkchecker import LinkCheckerTool
from rer.linkchecker.linkchecker import STATUS_BLACKLISTED
from rer.linkchecker.linkchecker import STATUS_CONNECTION_ERROR
from rer.linkchecker.linkchecker import STATUS_HTTPS_ONLY
from rer.linkchecker.linkchecker import STATUS_TIMEOUT
from rer.linkchecker.scripts.check_broken_links import check_link
from rer.linkchecker.scripts.check_broken_links import parse_args
from urllib3.exceptions import LocationParseError
from uuid import uuid4

import json
import pytest
import requests
import threading


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


class FakeManagedConnection:
    """The little RelStorage exposes of a database connection, as far as
    _drop_db_connections is concerned: a load connection is dropped, a store
    connection pool drops the connections it is keeping around."""

    def __init__(self):
        self.dropped = False

    def drop(self):
        self.dropped = True

    drop_all = drop


class FakeRelStorage:
    def __init__(self):
        self._load_connection = FakeManagedConnection()
        self._store_connection_pool = FakeManagedConnection()


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


class TestExtractLinks:
    """Real-world cases from the ambiente and salute reports, where the
    markup or the punctuation following a url ended up in the link."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            # the url is also the text of its own link
            (
                '<a href="https://a.it">https://a.it</a></span></p>',
                {"https://a.it"},
            ),
            # end of a sentence, also when the url is a bare host
            ("vedi http://federazione.lepida.it.", {"http://federazione.lepida.it"}),
            ("vedi https://a.it/x/y.", {"https://a.it/x/y"}),
            (
                "https://a.it, https://b.it; https://c.it!",
                {
                    "https://a.it",
                    "https://b.it",
                    "https://c.it",
                },
            ),
            ("'https://a.it/x'", {"https://a.it/x"}),
            # an unbalanced parenthesis belongs to the text...
            ("(vedi https://a.it/x)", {"https://a.it/x"}),
            ("(http://www.agenziafarmaco.it/),", {"http://www.agenziafarmaco.it/"}),
            ("(https://a.it/screening/cervice).", {"https://a.it/screening/cervice"}),
            # ...a balanced one to the url
            (
                "https://it.wikipedia.org/wiki/Foo_(bar)",
                {"https://it.wikipedia.org/wiki/Foo_(bar)"},
            ),
            (
                "(https://it.wikipedia.org/wiki/Foo_(bar))",
                {"https://it.wikipedia.org/wiki/Foo_(bar)"},
            ),
            # query strings, fragments and apostrophes inside a url are kept
            (
                "https://a.it/x?a=1&b=2;c=3#top",
                {"https://a.it/x?a=1&b=2;c=3#top"},
            ),
            (
                "https://it.wikipedia.org/wiki/Valle_d'Aosta",
                {"https://it.wikipedia.org/wiki/Valle_d'Aosta"},
            ),
            ("https://a.it:8080/x", {"https://a.it:8080/x"}),
            # resolveuid paths are untouched
            ("/resolveuid/abc-123.", {"resolveuid/abc-123"}),
        ],
    )
    def test_extract_links(self, text, expected):
        assert extract_links(text) == expected

    def test_blocks_serialized_as_json(self):
        """_find_links dumps the blocks to json: the escaped quotes of the
        html inside them still end the url, as they always did."""
        text = json.dumps({
            "value": '<a href="https://a.it/x">https://a.it/x</a>.',
            "url": "https://b.it/y?z=1",
        })
        assert extract_links(text) == {"https://a.it/x", "https://b.it/y?z=1"}

    def test_find_links_on_content(self, linkchecker_content):
        document = linkchecker_content["document"]
        document.blocks = {
            "abc": {
                "@type": "html",
                "html": (
                    '<p><span><a href="https://www.gruppolen.it">'
                    "https://www.gruppolen.it</a></span></p>"
                    "<p>Vedi http://federazione.lepida.it.</p>"
                ),
            }
        }
        links = linkchecker_content["tool"]._find_links(document)
        assert sorted(links) == [
            "http://federazione.lepida.it",
            "https://www.gruppolen.it",
        ]


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
        rows = list(tool.get_rows())
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
        rows = list(tool.get_rows())
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
        rows = list(tool.get_rows())
        blocked = [row for row in rows if row[3] == 999]
        assert len(blocked) == 1
        assert "Blocked by bot protection" in blocked[0][4]

    def test_get_broken_links_shape(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        now = datetime.now()
        tool._outgoing_links.clear()
        tool._outgoing_links[document.UID()] = (
            now,
            [
                ("https://example.com/fine", 200),  # never reported
                ("https://example.com/gone", 404),
                ("/resolveuid/deadbeef", 404),
                ("https://linkedin.com/x", 999),
            ],
        )
        items = list(tool.get_broken_links())
        assert [item["link"] for item in items] == [
            "https://example.com/gone",
            "/resolveuid/deadbeef",
            "https://linkedin.com/x",
        ]
        gone = items[0]
        assert gone["@id"] == document.absolute_url()
        assert gone["title"] == document.Title()
        assert gone["UID"] == document.UID()
        assert gone["link_type"] == "EXTERNAL"
        assert gone["status"] == 404
        assert gone["status_description"] == "Not Found"
        assert gone["action"] == "fix"
        assert gone["last_update"] == now
        assert items[1]["link_type"] == "INTERNAL"
        # bot-protected links are part of this view, unlike
        # get_page_with_broken_links: they carry their own description so a
        # report can tell "not verifiable" apart from "broken"
        assert "Blocked by bot protection" in items[2]["status_description"]
        # nobody classified 999: it falls in the remainder
        assert items[2]["action"] == "check"

    def test_get_rows_speaks_the_words_of_the_panel(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        tool._outgoing_links.clear()
        tool._outgoing_links[document.UID()] = (
            datetime.now(),
            [
                ("https://example.com/gone", 404),
                ("http://example.com/old", STATUS_HTTPS_ONLY),
                ("/resolveuid/deadbeef", 410),
                ("https://linkedin.com/x", 999),
            ],
        )
        header, *rows = tool.get_rows()
        assert header == [
            "Site content",
            "Link to check",
            "Link type",
            "Outcome",
            "Outcome description",
            "Link actions",
        ]
        assert [(row[2], row[3], row[5]) for row in rows] == [
            ("External", 404, "To fix"),
            ("External", STATUS_HTTPS_ONLY, "To update"),
            ("Internal", 410, "To fix"),
            # nobody classified 999: it still lands in "check"
            ("External", 999, "To check"),
        ]

    def test_get_broken_links_skips_deleted_content(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        tool._outgoing_links["gone-uid"] = (
            datetime.now(),
            [("https://example.com/broken", 404)],
        )
        assert not [
            item for item in tool.get_broken_links() if item["UID"] == "gone-uid"
        ]

    def test_filter_links(self, linkchecker_content):
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        tool._outgoing_links.clear()
        tool._outgoing_links[document.UID()] = (
            datetime.now(),
            [
                ("https://example.com/gone", 404),
                ("/resolveuid/deadbeef", 404),
                ("https://linkedin.com/x", 999),
            ],
        )
        items = list(tool.get_broken_links())

        by_status = list(tool.filter_links(items, status=[999]))
        assert [item["status"] for item in by_status] == [999]

        by_two_statuses = list(tool.filter_links(items, status=[404, 999]))
        assert len(by_two_statuses) == 3

        by_type = list(tool.filter_links(items, link_type="INTERNAL"))
        assert [item["link"] for item in by_type] == ["/resolveuid/deadbeef"]

        both = list(tool.filter_links(items, status=[404], link_type="EXTERNAL"))
        assert [item["link"] for item in both] == ["https://example.com/gone"]

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

    def test_unparsable_host_is_a_connection_error(self, linkchecker_content):
        """The real-world case of a link glued to the following markup: its
        host has a label longer than 63 chars, and urllib3 raises a
        LocationParseError that requests does not wrap."""
        tool = linkchecker_content["tool"]
        link = "https://ambiente.regione.emilia-romagna.it%3c" + "a" * 80
        session = FakeSession({link: LocationParseError(link)})
        assert (
            tool._fetch_status(link, timeout=1, headers={}, session=session)
            == STATUS_CONNECTION_ERROR
        )

    def test_the_relstorage_connections_are_dropped(self, linkchecker_content):
        """What _disconnect_db does when there *is* a connection to give back:
        the tests themselves run on a DemoStorage, which has none."""
        storage = FakeRelStorage()
        linkchecker_content["tool"]._drop_db_connections(storage)
        assert storage._load_connection.dropped
        assert storage._store_connection_pool.dropped

    def test_nothing_is_dropped_without_a_database_connection(
        self, linkchecker_content
    ):
        """A FileStorage (or the DemoStorage of the tests) is a local file:
        there is nothing to give back, and above all the transaction must be
        left alone -- committing here would persist whatever the caller had
        in flight."""
        assert linkchecker_content["tool"]._disconnect_db() is False


class RecordingSession(FakeSession):
    """A FakeSession that also keeps the timeout of every request."""

    def __init__(self, statuses):
        super().__init__(statuses)
        self.timeouts = []

    def head(self, url, verify=True, timeout=None, **kwargs):
        self.timeouts.append(timeout)
        return super().head(url, verify=verify, **kwargs)

    get = head


class FakeFetch:
    """Stands in for _fetch_status: ``statuses`` maps a host to the status
    every link of that host answers. Counts the requests per host."""

    def __init__(self, statuses):
        self.statuses = statuses
        self.calls = {}
        self.lock = threading.Lock()

    def __call__(self, link, timeout, headers, session=None, **kwargs):
        host = LinkCheckerTool._host_of(link)
        with self.lock:
            self.calls[host] = self.calls.get(host, 0) + 1
        return self.statuses[host]


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace the network with a FakeFetch, returned for the test to fill."""
    fetch = FakeFetch({})
    monkeypatch.setattr(LinkCheckerTool, "_fetch_status", staticmethod(fetch))
    return fetch


BACKEND = "applicazioni.regione.emilia-romagna.it"


class TestBlacklist:
    @pytest.mark.parametrize(
        "link,expected",
        [
            (f"https://{BACKEND}/x", True),
            # subdomains are covered, the case and the port do not matter
            (f"https://x.{BACKEND}/y", True),
            ("http://APPLICAZIONI.regione.emilia-romagna.it:8080/y", True),
            # a host that merely ends with the same letters is not
            ("https://notapplicazioni.regione.emilia-romagna.it/x", False),
            ("https://regione.emilia-romagna.it/x", False),
            ("https://example.org/?next=https://" + BACKEND, False),
        ],
    )
    def test_is_blacklisted(self, link, expected):
        assert is_blacklisted(link, (BACKEND, "other.it")) is expected

    @pytest.mark.parametrize(
        "link,expected",
        [
            # the editorial domains of every site
            ("https://ambiente-iam.regione.emilia-romagna.it/x", True),
            ("https://salute-iam.regione.emilia-romagna.it/x", True),
            ("https://AMBIENTE-IAM.regione.emilia-romagna.it:8080/x", True),
            # * spans dots: a subdomain of an editorial domain is one too
            ("https://www.ambiente-iam.regione.emilia-romagna.it/x", True),
            # the pattern is matched over the whole host
            ("https://iam.regione.emilia-romagna.it/x", False),
            ("https://ambiente.regione.emilia-romagna.it/x", False),
            ("https://ambiente-iam.regione.emilia-romagna.it.example.org/", False),
            ("https://ambiente-iam.example.org/x", False),
        ],
    )
    def test_is_blacklisted_by_pattern(self, link, expected):
        domains = ("*-iam.regione.emilia-romagna.it",)
        assert is_blacklisted(link, domains) is expected

    def test_the_blacklist_wins_over_the_domain_of_the_site(
        self, linkchecker_content, monkeypatch, fake_fetch
    ):
        """A check run on the editorial domain sees links to it as internal
        (portal_url): blacklisted, they are reported all the same."""
        tool = linkchecker_content["tool"]
        link = f"{tool.portal_url}/foo"
        monkeypatch.setenv(BLACKLIST_ENV, LinkCheckerTool._host_of(link))

        statuses = tool._check_links({"uid": [link]}, ttl=0, max_workers=1)

        assert statuses == {link: STATUS_BLACKLISTED}

    def test_domains_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv(BLACKLIST_ENV, f" {BACKEND.upper()} ,, other.it ")
        assert blacklisted_domains() == (BACKEND, "other.it")

    @pytest.mark.parametrize("value", [None, "", " , "])
    def test_no_domains(self, monkeypatch, value):
        if value is None:
            monkeypatch.delenv(BLACKLIST_ENV, raising=False)
        else:
            monkeypatch.setenv(BLACKLIST_ENV, value)
        assert blacklisted_domains() == ()
        assert not is_blacklisted(f"https://{BACKEND}/x", blacklisted_domains())

    def test_blacklisted_links_are_not_fetched(
        self, linkchecker_content, monkeypatch, fake_fetch
    ):
        monkeypatch.setenv(BLACKLIST_ENV, BACKEND)
        fake_fetch.statuses = {"example.org": 200}
        tool = linkchecker_content["tool"]
        links = [f"https://{BACKEND}/x", f"https://x.{BACKEND}/y"]

        statuses = tool._check_links(
            {"uid": [*links, "https://example.org/"]}, ttl=0, max_workers=1
        )

        assert statuses == {
            links[0]: STATUS_BLACKLISTED,
            links[1]: STATUS_BLACKLISTED,
            "https://example.org/": 200,
        }
        assert fake_fetch.calls == {"example.org": 1}
        # the blacklist may change any time: its answer is not cached
        assert links[0] not in tool._external_links_status

    def test_check_content_honors_the_blacklist(
        self, linkchecker_content, monkeypatch, fake_fetch
    ):
        monkeypatch.setenv(BLACKLIST_ENV, BACKEND)
        tool = linkchecker_content["tool"]
        document = linkchecker_content["document"]
        document.blocks = {"abc": {"@type": "html", "html": f"https://{BACKEND}/x"}}

        tool.check_content(document)

        assert tool._outgoing_links[document.UID()][1] == [
            (f"https://{BACKEND}/x", STATUS_BLACKLISTED)
        ]
        assert fake_fetch.calls == {}

    def test_the_script_honors_the_blacklist(
        self, linkchecker_content, monkeypatch, fake_fetch
    ):
        monkeypatch.setenv(BLACKLIST_ENV, BACKEND)
        args = parse_args(["check_broken_links"])
        assert check_link(
            linkchecker_content["tool"], args, f"https://{BACKEND}/x"
        ) == (
            "EXTERNAL",
            STATUS_BLACKLISTED,
        )
        assert fake_fetch.calls == {}

    def test_blacklisted_links_are_to_fix(self):
        assert LinkCheckerTool._action(STATUS_BLACKLISTED) == "fix"


class TestHostBreaker:
    def test_gives_up_after_consecutive_failures(self):
        breaker = HostBreaker(max_failures=3)
        for _ in range(2):
            breaker.record("dead.it", STATUS_CONNECTION_ERROR)
        assert breaker.skip("dead.it", "https://dead.it/1") is None
        breaker.record("dead.it", STATUS_CONNECTION_ERROR)
        assert breaker.skip("dead.it", "https://dead.it/2") == STATUS_CONNECTION_ERROR
        assert breaker.skipped == {"https://dead.it/2"}
        # the other hosts are not touched
        assert breaker.skip("ok.it", "https://ok.it/") is None

    @pytest.mark.parametrize("answer", [404, 502, STATUS_TIMEOUT])
    def test_any_answer_resets_the_count(self, answer):
        """An http error, or a page too slow to answer, still proves the host
        accepts connections."""
        breaker = HostBreaker(max_failures=3)
        for status in (
            STATUS_CONNECTION_ERROR,
            STATUS_CONNECTION_ERROR,
            answer,
            STATUS_CONNECTION_ERROR,
        ):
            breaker.record("flaky.it", status)
        assert breaker.skip("flaky.it", "https://flaky.it/") is None

    def test_timeouts_never_give_a_host_up(self):
        """The real-world case of applicazioni.regione… on ambiente: 200, 502
        or a timeout depending on the page. Given up on after three slow
        pages in a row, it had 28 working links reported as timeouts."""
        breaker = HostBreaker(max_failures=3)
        for _ in range(10):
            breaker.record("slow.it", STATUS_TIMEOUT)
        assert breaker.skip("slow.it", "https://slow.it/working") is None

    @pytest.mark.parametrize("max_failures", [0, -1])
    def test_can_be_disabled(self, max_failures):
        breaker = HostBreaker(max_failures=max_failures)
        for _ in range(10):
            breaker.record("dead.it", STATUS_CONNECTION_ERROR)
        assert breaker.skip("dead.it", "https://dead.it/") is None

    def test_a_dead_host_is_given_up_on(self, linkchecker_content, fake_fetch):
        fake_fetch.statuses = {"dead.it": STATUS_CONNECTION_ERROR, "ok.it": 200}
        tool = linkchecker_content["tool"]
        dead = [f"https://dead.it/{i}" for i in range(10)]

        statuses = tool._check_external_links(
            {*dead, "https://ok.it/"}, ttl=0, max_workers=1, host_max_failures=3
        )

        assert fake_fetch.calls == {"dead.it": 3, "ok.it": 1}
        assert all(statuses[link] == STATUS_CONNECTION_ERROR for link in dead)
        assert statuses["https://ok.it/"] == 200
        # only what was fetched is cached: the skipped links are tried again
        # next time
        assert sum(link in tool._external_links_status for link in dead) == 3

    def test_given_up_on_in_the_worker_threads(self, linkchecker_content, fake_fetch):
        """With max_per_host requests in flight when the host is given up on,
        at most max_per_host - 1 more go out after the one that tripped it."""
        fake_fetch.statuses = {"dead.it": STATUS_CONNECTION_ERROR}
        dead = {f"https://dead.it/{i}" for i in range(50)}

        statuses = linkchecker_content["tool"]._check_external_links(
            dead, ttl=0, max_workers=8, max_per_host=2, host_max_failures=3
        )

        assert fake_fetch.calls["dead.it"] <= 4
        assert set(statuses.values()) == {STATUS_CONNECTION_ERROR}

    def test_a_slow_host_is_checked_link_by_link(self, linkchecker_content, fake_fetch):
        fake_fetch.statuses = {"slow.it": STATUS_TIMEOUT}
        slow = {f"https://slow.it/{i}" for i in range(10)}
        linkchecker_content["tool"]._check_external_links(
            slow, ttl=0, max_workers=1, host_max_failures=3
        )
        assert fake_fetch.calls == {"slow.it": 10}

    def test_disabled_fetches_everything(self, linkchecker_content, fake_fetch):
        fake_fetch.statuses = {"dead.it": STATUS_CONNECTION_ERROR}
        dead = {f"https://dead.it/{i}" for i in range(10)}
        linkchecker_content["tool"]._check_external_links(
            dead, ttl=0, max_workers=1, host_max_failures=0
        )
        assert fake_fetch.calls == {"dead.it": 10}


class TestTimeouts:
    def test_connect_and_read_timeouts(self, linkchecker_content):
        session = RecordingSession({"https://foo.com/bar": 404})
        linkchecker_content["tool"]._fetch_status(
            "https://foo.com/bar",
            timeout=15,
            headers={},
            session=session,
            connect_timeout=5,
        )
        # HEAD, then the GET double check of the 404
        assert session.timeouts == [(5, 15), (5, 15)]

    def test_connect_timeout_never_exceeds_the_timeout(self, linkchecker_content):
        session = RecordingSession({"https://foo.com/bar": 200})
        linkchecker_content["tool"]._fetch_status(
            "https://foo.com/bar", timeout=3, headers={}, session=session
        )
        assert session.timeouts == [(3, 3)]

    def test_a_connect_timeout_is_a_connection_error(self, linkchecker_content):
        """The host did not even accept the connection: raising the timeout,
        which a STATUS_TIMEOUT suggests, would not help."""
        tool = linkchecker_content["tool"]
        session = FakeSession({
            "https://foo.com/bar": requests.exceptions.ConnectTimeout("syn")
        })
        assert (
            tool._fetch_status(
                "https://foo.com/bar", timeout=1, headers={}, session=session
            )
            == STATUS_CONNECTION_ERROR
        )
        session = FakeSession({
            "https://foo.com/bar": requests.exceptions.ReadTimeout("slow")
        })
        assert (
            tool._fetch_status(
                "https://foo.com/bar", timeout=1, headers={}, session=session
            )
            == STATUS_TIMEOUT
        )
