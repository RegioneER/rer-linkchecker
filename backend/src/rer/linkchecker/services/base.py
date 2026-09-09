from plone import api
from plone.restapi.services import Service
from zExceptions import BadRequest


LINK_TYPES = ("INTERNAL", "EXTERNAL")


class LinkcheckerService(Service):
    """Base class for the report endpoints.

    Both endpoints only ever read what the last check stored: they never call
    check_site, because a full check takes minutes on a medium site and would
    time out the request. The data is refreshed out of band, by the
    check_broken_links script (cron), which is why the responses carry the
    timestamp of the data they serve.
    """

    @property
    def tool(self):
        return api.portal.get_tool("portal_linkchecker")

    def filters(self):
        """Parse the query string filters shared by both endpoints.

        An invalid value raises rather than being ignored: an explicit error
        beats silently answering with an empty report.

        :return: dict of keyword arguments for tool.get_broken_links
        """
        return {
            "status": self._status_filter(),
            "link_type": self._link_type_filter(),
        }

    def _status_filter(self):
        """``?status=404&status=-2`` -> [404, -2]

        Zope hands over a single string or a list depending on how many times
        the parameter is repeated, so normalize to a list. Values may be
        negative (see the STATUS_* constants in linkchecker.py).
        """
        value = self.request.form.get("status")
        if not value:
            return None
        values = value if isinstance(value, list) else [value]
        try:
            return [int(item) for item in values]
        except (TypeError, ValueError):
            # from None: the caller gets our message, not a ValueError traceback
            raise BadRequest(
                f"Invalid status filter: {values!r}. Expected integers, "
                "e.g. status=404 (negative values are the STATUS_* constants)."
            ) from None

    def _link_type_filter(self):
        """``?type=EXTERNAL`` -> "EXTERNAL" """
        value = self.request.form.get("type")
        if not value:
            return None
        link_type = value.upper()
        if link_type not in LINK_TYPES:
            raise BadRequest(
                f"Invalid type filter: {value!r}. Expected one of "
                f"{', '.join(LINK_TYPES)}."
            )
        return link_type
