# rer.linkchecker

A Plone addon that checks every internal and external link found in site contents (fields and Volto blocks) and generates a report of the broken ones.

## Features

- Adds a `portal_linkchecker` tool that crawls the whole site, collecting every link found in content fields and in Volto blocks (`resolveuid/...` links included).
- Checks internal links by resolving them against the catalog, and external links concurrently over HTTP (configurable timeout, thread pool size, and per-host throttling).
- Caches external link statuses for a configurable TTL, so repeated runs only re-check links that are due.
- Distinguishes real broken links from bot-protection responses (`403`, `429`, LinkedIn's `999`) and from `http://` links that only work over `https://` (reported so they can be fixed in place, not counted as broken).
- Reports the conditions that are not a plain http status with their own negative status, so they can be told apart in the CSV: `-1` timeout, `-2` works only over `https` (update the link), `-3` connection error.
- Does not verify TLS certificates: only reachability matters here, and many otherwise working servers omit their intermediate certificate (browsers fetch it themselves, `requests` does not), which would be reported as a broken link.
- Exposes the results as a CSV report (`PAGE, LINK, TYPE, STATUS, DESCRIPTION`) via `tool.get_rows()`.
- Ships a `check_broken_links` console script to run a check from the command line or from cron, without going through the web.

## Installation

Install `rer.linkchecker` with uv:

```shell
uv add rer.linkchecker
```

or add it to a zc.buildout-based project as a develop egg / source, alongside `plone.volto` (required: it provides the `blocks`/`blocks_layout` fields the linkchecker scans, and `plone.distribution` used by `addPloneSite`).

Then add `rer.linkchecker` to the `eggs` of your Plone instance and install the add-on from the Plone control panel (or via a GenericSetup profile) as usual.

## Usage

### The `portal_linkchecker` tool

```python
from plone import api

tool = api.portal.get_tool("portal_linkchecker")
tool.check_site()  # crawl the whole site and check every link

for uid, broken_links in tool.get_page_with_broken_links():
    ...  # [(link, status), ...] per content UID

import csv

with open("broken_links.csv", "w", newline="") as fh:
    writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
    for row in tool.get_rows(broken=True):
        writer.writerow(row)
```

`check_site(ttl=3600 * 6, timeout=15, max_workers=10)` accepts:

- `ttl`: seconds a cached external link status stays valid (`0` forces a full recheck).
- `timeout`: per-request timeout, in seconds, for external links.
- `max_workers`: number of concurrent threads checking external links.

### The `check_broken_links` console script

Installed as a standard `console_scripts` entry point (`[project.scripts]` in `pyproject.toml`), so it lands in `bin/` both in a uv-managed virtualenv and in a zc.buildout instance. Since it runs Zope/ZODB code, it must be launched through `zconsole`/`instance run`, not called directly:

```shell
# uv-managed instance (Makefile: make check-broken-links)
./bin/zconsole run instance/etc/zope.conf ./.venv/bin/check_broken_links

# zc.buildout instance
./bin/instance run bin/check_broken_links
```

Options:

- `--ttl`, `--workers`, `--timeout`: same meaning as on `check_site()`.
- `--output-dir`: directory where the csv report is written (default: cwd).
- `--site-id`: id of the Plone site to check (default: the `PLONE_SITE_ID` env var, or `Plone`).
- `--url <url>`: verify a single url and log its status, without touching the site.
- `--content <path-or-UID>`: verify a single content's links and log them, without touching the site.

The csv is written to `<output-dir>/<siteid>_broken_links_<YYYYMMDD-HHMMSS>.csv`.

## Development

### Prerequisites

- An [operating system](https://6.docs.plone.org/install/create-project-cookieplone.html#prerequisites-for-installation) that runs all the requirements mentioned.
- [uv](https://6.docs.plone.org/install/create-project-cookieplone.html#uv)
- [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make)
- [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git)
- [Docker](https://docs.docker.com/get-started/get-docker/) (optional)

### Setup

```shell
git clone git@github.com:RegioneEr/rer-linkchecker.git
cd rer-linkchecker/backend
make install
```

### Common tasks

```shell
make start                  # start a Plone instance on localhost:8080
make create-site            # create a new site from scratch
make check-broken-links     # run the linkchecker and write a csv report
make test                   # run the test suite
```

## Contribute

- [Issue tracker](https://github.com/RegioneEr/rer-linkchecker/issues)
- [Source code](https://github.com/RegioneEr/rer-linkchecker/)

## License

The project is licensed under GPLv2.

## Credits

Developed with the support of [Regione Emilia Romagna](http://www.regione.emilia-romagna.it/).

Regione Emilia Romagna supports the [PloneGov initiative](http://www.plonegov.it/).

## Authors

This product was developed by **RedTurtle Technology** team.

[![RedTurtle Technology](https://avatars1.githubusercontent.com/u/1087171?s=100&v=4)](http://www.redturtle.it/)
