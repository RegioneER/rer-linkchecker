"""Run the portal_linkchecker over a Plone site and store the report of the
broken links. Same logic as the @@find-broken-links view, but runnable
from the command line / cron. This module backs the ``check_broken_links``
console script registered in pyproject.toml, so it is invoked as:

    ZCONSOLE="./bin/zconsole run instance/etc/zope.conf"
    $ZCONSOLE ./.venv/bin/check_broken_links
    $ZCONSOLE ./.venv/bin/check_broken_links --ttl 0 --workers 20
    $ZCONSOLE ./.venv/bin/check_broken_links --output-dir /tmp

or, in a zc.buildout instance:

    ./bin/instance run bin/check_broken_links

The installed console script only *imports* this module rather than exec'ing
it, so it cannot rely on the ``app`` name that ``zconsole``/``instance run``
inject into the top-level script's namespace: that injection is invisible to
a separately imported module. Instead ``run()`` bootstraps its own root
object exactly like ``Zope2.utilities.zconsole.runscript`` does.

Targets the site with id ``PLONE_SITE_ID`` (default ``Plone``); use
``--site-id`` to target a different one.

The result is stored in the site and read back from there, by the
``@linkchecker`` / ``@linkchecker-csv`` endpoints: this script only refreshes
it. Pass ``--output-dir`` to also dump the run as a csv (PAGE, LINK, TYPE,
STATUS, DESCRIPTION) in <output-dir>/<siteid>_broken_links_<YYYYMMDD-HHMMSS>.csv,
whose timestamp keeps each run's file distinct: useful to keep an archive of
past runs, which the site only ever holds for the last one.
"""

from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.users import system as system_user
from datetime import datetime
from plone import api
from rer.linkchecker.linkchecker import DEFAULT_TIMEOUT
from rer.linkchecker.linkchecker import format_duration
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

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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
        default=None,
        help="also dump the run as a csv in this directory (default: no csv, "
        "since the stored report is served by the @linkchecker-csv endpoint).",
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

        # spelled out as the call it is: with no flags the dict repr would log
        # a puzzling "check_site({})", which reads like a wrong argument
        options = ", ".join(f"{name}={value}" for name, value in kwargs.items())
        logger.info("## [%s] start check_site(%s) ##", site_id, options)
        tool.check_site(**kwargs)
        commit()

        broken = sum(1 for _ in tool.get_broken_links())
        output = write_csv(tool, site_id, args.output_dir)
        logger.info(
            "## [%s] done in %s, %d broken links%s ##",
            site_id,
            format_duration(tool._last_duration),
            broken,
            f" -> {output}" if output else "",
        )


def write_csv(tool, site_id, output_dir):
    """Dump the stored report as a csv file, and return its path.

    Only when asked for: the report lives in the site and is served by the
    @linkchecker-csv endpoint, which renders these very same rows, so the file
    is an archive of this run rather than the way to read the result.
    """
    if not output_dir:
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = os.path.join(output_dir, f"{site_id}_broken_links_{timestamp}.csv")
    with open(output, "w", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        for row in tool.get_rows():
            writer.writerow(row)
    return output


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


def setup_logging():
    """Log at INFO, with a timestamp on every line.

    The timestamp is the point of it: a full check takes minutes, logs its
    progress every 5%, and from cron the log is all that is left of the run —
    without an absolute time there is no telling how long a phase took, nor
    when the run that produced a given report actually happened.

    Every root handler is reformatted, since the interesting one is whatever
    zconsole / ``instance run`` installed, and this process is the script.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    for handler in root.handlers:
        handler.setLevel(logging.INFO)
        handler.setFormatter(formatter)


def run():
    setup_logging()

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
