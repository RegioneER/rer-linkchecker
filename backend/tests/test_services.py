from datetime import datetime
from io import StringIO
from plone import api

import csv
import pytest
import transaction


LAST_UPDATE = datetime(2026, 7, 30, 3, 0, 12)


@pytest.fixture
def tool(functional_portal):
    return api.portal.get_tool("portal_linkchecker")


@pytest.fixture
def report(functional_portal, tool):
    """Store a report on the tool, as the nightly check would have left it."""
    portal = functional_portal
    with api.env.adopt_roles(["Manager"]):
        page = api.content.create(container=portal, type="Document", title="Una pagina")
        other = api.content.create(
            container=portal, type="Document", title="Altra pagina"
        )
    tool._outgoing_links[page.UID()] = (
        LAST_UPDATE,
        [
            ("https://example.com/gone", 404),
            ("https://example.com/fine", 200),  # not broken: never reported
            ("/resolveuid/deadbeef", 404),  # internal
            ("https://linkedin.com/x", 999),  # blocked, still reported
        ],
    )
    tool._outgoing_links[other.UID()] = (
        LAST_UPDATE,
        [("https://example.com/also-gone", 404)],
    )
    tool._last_update = LAST_UPDATE
    tool._last_duration = 412.7
    transaction.commit()
    yield {"page": page, "other": other}
    with api.env.adopt_roles(["Manager"]):
        tool.clear()
    transaction.commit()


class TestReportService:
    def test_anonymous_is_rejected(self, report, anon_request):
        assert anon_request.get("/@linkchecker").status_code == 401

    def test_manager_gets_the_stored_report(self, report, manager_request):
        response = manager_request.get("/@linkchecker")
        assert response.status_code == 200
        data = response.json()
        # the 200 link is not part of the report, the blocked 999 is
        assert data["items_total"] == 4
        assert len(data["items"]) == 4
        assert data["duration"] == 412.7
        # tells the reader how old the data is, the check runs out of band
        assert data["last_update"] == LAST_UPDATE.isoformat()

    def test_item_shape(self, report, manager_request):
        items = manager_request.get("/@linkchecker").json()["items"]
        item = next(item for item in items if item["link"].endswith("/gone"))
        assert item["@id"] == report["page"].absolute_url()
        assert item["@type"] == "Document"
        assert item["title"] == "Una pagina"
        assert item["UID"] == report["page"].UID()
        assert item["link_type"] == "EXTERNAL"
        assert item["status"] == 404
        assert item["status_description"] == "Not Found"
        assert item["last_update"] == LAST_UPDATE.isoformat()
        # internal links are told apart, they are fixed in a different way
        internal = [item for item in items if item["link_type"] == "INTERNAL"]
        assert [item["link"] for item in internal] == ["/resolveuid/deadbeef"]

    def test_summary_counts_every_status(self, report, manager_request):
        summary = manager_request.get("/@linkchecker").json()["summary"]
        assert summary == [
            {"status": 404, "status_description": "Not Found", "count": 3},
            {
                "status": 999,
                "status_description": (
                    "Blocked by bot protection (works for a human, not verifiable)"
                ),
                "count": 1,
            },
        ]

    def test_never_checked_is_told_apart_from_nothing_broken(
        self, functional_portal, manager_request
    ):
        data = manager_request.get("/@linkchecker").json()
        assert data["last_update"] is None
        assert data["duration"] is None
        assert data["items"] == []
        assert data["summary"] == []

    def test_reading_the_report_never_runs_a_check(self, report, tool, manager_request):
        """The whole point of these endpoints: a check takes minutes, so they
        only ever serve what is already stored."""
        manager_request.get("/@linkchecker")
        manager_request.get("/@linkchecker-csv")
        tool._p_jar.sync()
        assert len(tool._external_links_status) == 0
        assert tool._last_update == LAST_UPDATE


class TestReportFilters:
    def test_filter_by_status(self, report, manager_request):
        data = manager_request.get("/@linkchecker?status=999").json()
        assert [item["status"] for item in data["items"]] == [999]
        assert data["items_total"] == 1

    def test_filter_by_repeated_status(self, report, manager_request):
        data = manager_request.get("/@linkchecker?status=404&status=999").json()
        assert data["items_total"] == 4

    def test_filter_by_type(self, report, manager_request):
        data = manager_request.get("/@linkchecker?type=INTERNAL").json()
        assert [item["link"] for item in data["items"]] == ["/resolveuid/deadbeef"]

    def test_summary_ignores_the_active_filters(self, report, manager_request):
        """A UI builds its filter chips from the summary: the counts would be
        useless if they changed every time a filter is applied."""
        data = manager_request.get("/@linkchecker?status=999").json()
        assert data["items_total"] == 1
        assert [entry["count"] for entry in data["summary"]] == [3, 1]

    @pytest.mark.parametrize(
        "query", ["status=abc", "status=404&status=abc", "type=PIPPO"]
    )
    def test_invalid_filter_is_an_explicit_error(self, report, manager_request, query):
        """Better a clear 400 than silently answering with an empty report."""
        assert manager_request.get(f"/@linkchecker?{query}").status_code == 400


class TestReportBatching:
    def test_batching_links_keep_the_filters(self, report, manager_request):
        data = manager_request.get("/@linkchecker?status=404&b_size=2").json()
        assert len(data["items"]) == 2
        assert data["items_total"] == 3
        assert "status=404" in data["batching"]["next"]
        assert "b_start=2" in data["batching"]["next"]

    def test_no_batching_links_when_it_all_fits(self, report, manager_request):
        assert "batching" not in manager_request.get("/@linkchecker").json()


class TestCsvService:
    def test_anonymous_is_rejected(self, report, anon_request):
        assert anon_request.get("/@linkchecker-csv").status_code == 401

    def test_csv_is_served_as_a_download(self, report, manager_request):
        response = manager_request.get("/@linkchecker-csv")
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
        disposition = response.headers["Content-Disposition"]
        assert disposition.startswith("attachment; filename=")
        # the file name carries the date of the data, not of the download
        assert "20260730-030012" in disposition
        assert response.headers["X-Linkchecker-Last-Update"] == LAST_UPDATE.isoformat()

    def test_csv_matches_the_one_the_script_writes(self, report, tool, manager_request):
        """Enforced rather than assumed: the endpoint must not drift from the
        csv produced by the check_broken_links script."""
        expected = StringIO()
        writer = csv.writer(expected, quoting=csv.QUOTE_ALL)
        for row in tool.get_rows():
            writer.writerow(row)
        assert manager_request.get("/@linkchecker-csv").text == expected.getvalue()

    def test_csv_honors_the_filters(self, report, manager_request):
        body = manager_request.get("/@linkchecker-csv?type=INTERNAL").text
        assert "/resolveuid/deadbeef" in body
        assert "example.com" not in body

    def test_never_checked_has_a_filename_without_a_date(
        self, functional_portal, manager_request
    ):
        response = manager_request.get("/@linkchecker-csv")
        assert response.status_code == 200
        assert "_broken_links_unknown.csv" in response.headers["Content-Disposition"]
        assert "X-Linkchecker-Last-Update" not in response.headers


class TestPermission:
    def test_editor_can_read_the_report(self, report, request_factory):
        """The report is for whoever fixes the content, not only for managers:
        that is why it has its own permission instead of cmf.ManagePortal."""
        with api.env.adopt_roles(["Manager"]):
            api.user.create(
                email="editor@example.com",
                username="editor",
                password="secret-editor",  # noqa: S106 - throwaway test user
            )
            # granted apart: addMember only lets you hand out roles you hold
            api.user.grant_roles(username="editor", roles=["Editor"])
        transaction.commit()
        session = request_factory(basic_auth=("editor", "secret-editor"))
        assert session.get("/@linkchecker").status_code == 200
        assert session.get("/@linkchecker-csv").status_code == 200
