"""Run the portal_linkchecker over a Plone site and dump a csv report of
the broken links. Same logic as the @@find-broken-links view, but runnable
from the command line / cron. This module backs the ``check_broken_links``
console script registered in pyproject.toml, so it is invoked as:

    ./bin/zconsole run instance/etc/zope.conf ./.venv/bin/check_broken_links
    ./bin/zconsole run instance/etc/zope.conf ./.venv/bin/check_broken_links --ttl 0 --workers 20
    ./bin/zconsole run instance/etc/zope.conf ./.venv/bin/check_broken_links --output-dir /tmp

or, in a zc.buildout instance:

    ./bin/instance run bin/check_broken_links

The installed console script only *imports* this module rather than exec'ing
it, so it cannot rely on the ``app`` name that ``zconsole``/``instance run``
inject into the top-level script's namespace: that injection is invisible to
a separately imported module. Instead ``run()`` bootstraps its own root
object exactly like ``Zope2.utilities.zconsole.runscript`` does.

Targets the site with id ``PLONE_SITE_ID`` (default ``Plone``); use ``--site-id`` to target a different one.

The csv (PAGE, LINK, TYPE, STATUS, DESCRIPTION) is written to
<output-dir>/<siteid>_broken_links_<YYYYMMDD-HHMMSS>.csv (default: current
directory); the timestamp keeps each run's report distinct.
"""

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.users import system as system_user
from datetime import datetime
from plone import api
from rer.linkchecker.linkchecker import DEFAULT_TIMEOUT
from Testing.makerequest import makerequest
from transaction import commit
from zope.component.hooks import setSite
from zope.globalrequest import setRequest

import argparse
import csv
import logging
import os
import sys
import Zope2

logger = logging.getLogger("check_broken_links")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="check_broken_links",
        description="Check broken links on a Plone site and write a csv.",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=None,
        help="seconds a cached external link status stays valid "
        "(default: the tool default, 6h). Use 0 to force a full recheck.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="number of concurrent threads checking external links "
        "(default: the tool default, 10).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="per-request timeout in seconds (default: the tool default, 15).",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getcwd(),
        help="directory where the csv files are written (default: cwd).",
    )
    parser.add_argument(
        "--site-id",
        default=os.getenv("PLONE_SITE_ID", "Plone"),
        help="id of the Plone site to check (default: the PLONE_SITE_ID env "
        "var, or 'Plone').",
    )
    single = parser.add_mutually_exclusive_group()
    single.add_argument(
        "--content",
        default=None,
        help="verify a single content by path (e.g. /Plone/foo) or UID, "
        "print its links and exit (no csv, no changes stored).",
    )
    single.add_argument(
        "--url",
        default=None,
        help="verify a single url, print its status and exit "
        "(no csv, no changes stored).",
    )
    return parser.parse_args(_script_args(argv))


def _script_args(argv):
    """Return only the args meant for this script.

    ``zconsole run`` leaves sys.argv as
    ``[.../interpreter, -c, <script>, --ttl, 0]``, where ``<script>`` is
    either a repo-relative path (e.g. ``scripts/check_broken_links.py``) or
    the ``check_broken_links`` console script installed by this package
    (e.g. ``.venv/bin/check_broken_links``). Keep whatever comes after it.
    """
    for i, arg in enumerate(argv):
        base = os.path.basename(arg)
        if base in ("check_broken_links", "check_broken_links.py"):
            return argv[i + 1 :]
    return argv[1:]


def check_site_report(site, args):
    setSite(site)
    site_id = site.getId()
    with api.env.adopt_user(username="admin"):
        tool = api.portal.get_tool("portal_linkchecker")

        # only pass options the user actually set, so the tool defaults apply
        kwargs = {}
        if args.ttl is not None:
            kwargs["ttl"] = args.ttl
        if args.timeout is not None:
            kwargs["timeout"] = args.timeout
        if args.workers is not None:
            kwargs["max_workers"] = args.workers

        logger.info("## [%s] start check_site(%s) ##", site_id, kwargs)
        tool.check_site(**kwargs)
        commit()

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = os.path.join(
            args.output_dir, f"{site_id}_broken_links_{timestamp}.csv"
        )
        rows = 0
        with open(output, "w", newline="") as fh:
            writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
            for row in tool.get_rows(broken=True):
                writer.writerow(row)
                rows += 1
        # rows includes the header line
        logger.info(
            "## [%s] done in %ss, %d broken links -> %s ##",
            site_id,
            tool._last_duration,
            max(rows - 1, 0),
            output,
        )


def check_single_url(tool, args, url):
    """Verify a single url and log its status (nothing is stored)."""
    timeout = args.timeout if args.timeout is not None else DEFAULT_TIMEOUT
    if tool._is_internal(url):
        link_type = "INTERNAL"
        status = tool._check_internal_link(url)
    else:
        link_type = "EXTERNAL"
        status = tool._fetch_status(url, timeout=timeout, headers=tool.request_headers)
    logger.info(
        "%s  %s  %s  %s",
        url,
        link_type,
        status,
        tool._status_description(status),
    )


def check_single_content(tool, args, obj):
    """Verify a single content's links and log them (nothing is stored)."""
    timeout = args.timeout if args.timeout is not None else DEFAULT_TIMEOUT
    logger.info("## Links for %s ##", obj.absolute_url())
    for link in tool._find_links(obj):
        if tool._is_internal(link):
            link_type = "INTERNAL"
            status = tool._check_internal_link(link)
        else:
            link_type = "EXTERNAL"
            status = tool._fetch_status(
                link, timeout=timeout, headers=tool.request_headers
            )
        logger.info(
            "  %s  %s  %s  %s",
            link,
            link_type,
            status,
            tool._status_description(status),
        )


def _bootstrap_app():
    """Get the Zope root object, same as Zope2.utilities.zconsole.runscript.

    Needed because this module is *imported* by the installed console
    script rather than exec'd by zconsole/instance run, so it can't rely on
    the ``app`` name they inject into the top-level script's namespace.
    """
    app = Zope2.app()
    app = makerequest(app)
    app.REQUEST["PARENTS"] = [app]
    setRequest(app.REQUEST)
    newSecurityManager(None, system_user)
    return app


def run():
    logging.getLogger().setLevel(logging.INFO)
    for handler in logging.getLogger().handlers:
        handler.setLevel(logging.INFO)

    args = parse_args(list(sys.argv))

    app = _bootstrap_app()
    site = app.get(args.site_id)
    if site is None:
        logger.warning("Plone site not found: %s", args.site_id)
        return

    # single-content / single-url modes: verify and exit, no csv/commit
    if args.url or args.content:
        setSite(site)
        with api.env.adopt_user(username="admin"):
            tool = api.portal.get_tool("portal_linkchecker")
            if args.url:
                check_single_url(tool, args, args.url)
                return
            obj = api.content.get(UID=args.content) or api.content.get(
                path=args.content
            )
            if obj is None:
                logger.warning("Content not found: %s", args.content)
                return
            check_single_content(tool, args, obj)
    else:
        check_site_report(site, args)


if __name__ == "__main__":
    run()
