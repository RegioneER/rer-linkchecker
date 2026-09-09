from .base import LinkcheckerService
from .report import isoformat
from io import StringIO
from plone import api

import csv


class LinkcheckerCsv(LinkcheckerService):
    """GET @linkchecker-csv: the stored report as a csv download.

    Honors the same filters as @linkchecker: whoever narrows the report down in
    a UI and then hits download expects to get what they are looking at.
    """

    def render(self):
        # render, not reply: Service.render json encodes whatever reply returns
        self.check_permission()
        tool = self.tool
        last_update = tool._last_update

        out = StringIO()
        writer = csv.writer(out, quoting=csv.QUOTE_ALL)
        for row in tool.get_rows(**self.filters()):
            writer.writerow(row)

        response = self.request.response
        response.setHeader("Content-Type", "text/csv; charset=utf-8")
        response.setHeader(
            "Content-Disposition",
            f'attachment; filename="{self.filename(last_update)}"',
        )
        if last_update is not None:
            # the age of the data, without having to parse the file name
            response.setHeader("X-Linkchecker-Last-Update", isoformat(last_update))
        return out.getvalue()

    @staticmethod
    def filename(last_update):
        """Same shape as the csv the check_broken_links script writes, but
        stamped with the date of the data rather than of the download."""
        site_id = api.portal.get().getId()
        stamp = last_update.strftime("%Y%m%d-%H%M%S") if last_update else "unknown"
        return f"{site_id}_broken_links_{stamp}.csv"
