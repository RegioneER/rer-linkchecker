from .base import LinkcheckerService
from plone.restapi.batching import HypermediaBatch


def isoformat(value):
    """ISO 8601 for a naive datetime, None if there is none.

    Not plone.restapi's json_compatible: that goes through an adapter lookup
    and the stored values are plain datetime.datetime from datetime.now().
    """
    return value.isoformat() if value is not None else None


class LinkcheckerReport(LinkcheckerService):
    """GET @linkchecker: the stored report as json, filterable and batched."""

    def reply(self):
        tool = self.tool
        # one walk: the summary counts the whole report, items show a subset
        all_items = list(tool.get_broken_links())
        results = list(tool.filter_links(all_items, **self.filters()))
        batch = HypermediaBatch(self.request, results)

        data = {
            "@id": batch.canonical_url,
            # the report is built out of band by the check_broken_links script,
            # so tell the reader how old the data they are looking at is
            "last_update": isoformat(tool._last_update),
            "duration": tool._last_duration,
            "items_total": batch.items_total,
            "summary": self.summary(all_items),
            "items": [self.serialize(item) for item in batch],
        }
        links = batch.links
        if links is not None:
            data["batching"] = links
        return data

    def summary(self, items):
        """Count the links per status, over the *unfiltered* report.

        Kept independent of the active filters on purpose: these counts are
        what a UI builds its filter chips from, and they would be useless if
        they changed every time a filter is applied. A list of objects rather
        than a status -> count mapping, so the label comes with the count and
        json keys stay out of the way. The label reuses the item field name, so
        a chip and a row render the same string from the same key.
        """
        counts = {}
        descriptions = {}
        for item in items:
            status = item["status"]
            counts[status] = counts.get(status, 0) + 1
            descriptions[status] = item["status_description"]
        return [
            {
                "status": status,
                "status_description": descriptions[status],
                "count": count,
            }
            for status, count in sorted(
                counts.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]

    @staticmethod
    def serialize(item):
        return dict(item, last_update=isoformat(item["last_update"]))
