# RER: Link checker (@regioneer/volto-rer-linkchecker)

Volto add-on that shows editors a report of the broken and outdated links found in the site contents, so they can fix them.

[![npm](https://img.shields.io/npm/v/@regioneer/volto-rer-linkchecker)](https://www.npmjs.com/package/@regioneer/volto-rer-linkchecker)
[![CI](https://github.com/RegioneER/rer-linkchecker/actions/workflows/main.yml/badge.svg)](https://github.com/RegioneER/rer-linkchecker/actions/workflows/main.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](#license)

This is the frontend part of [rer-linkchecker](https://github.com/RegioneER/rer-linkchecker).
The links are checked by the Plone add-on [`rer.linkchecker`](https://github.com/RegioneER/rer-linkchecker/tree/main/backend), which must be installed on the backend: this package only displays its results.

## Features

- A **"Site link check" page** at `/controlpanel/linkchecker`, with the links found by the last check, internal and external.
- A **"Check links" entry in the user menu** of the Volto toolbar, shown only to the users allowed to see the report.
- Each link is grouped by the **action the editor has to take**:
  - **To fix**: the link leads to a resource that is not available (`404`, `410`). Remove or replace it.
  - **To update**: the link works but uses `http` instead of `https`. Edit the URL.
  - **To check**: the link could not be verified automatically (timeouts, connection errors, bot protection, server errors...). Check it by hand.
- **Filters** by action (each option shows how many links it contains) and by link type (internal or external).
- For each link, the report shows the content that contains it, the link itself and a human-readable description of the outcome (for example "Resource not found" or "Invalid security certificate").
- **Pagination**, with page sizes of the site default, 50 or 100 items.
- **CSV export** of the report, with the filters currently applied.
- The date and time of the last check, and distinct messages when no check has run yet or when no broken links were found.

## Requirements

| Component | Version |
| --- | --- |
| Volto | 19 (developed and tested on 19.3) |
| React | 18 |
| Node.js | 22 or 24 |
| Plone backend | 6.1 or 6.2, with [`rer.linkchecker`](https://github.com/RegioneER/rer-linkchecker/tree/main/backend) installed |

## Installation

### 1. Backend

Install the `rer.linkchecker` Python package in your Plone backend and activate it in the add-ons control panel (or import the `rer.linkchecker:default` profile).

The check itself does not run from the browser: it is launched by the `check_broken_links` console script, usually scheduled once a day with cron.
See the [backend documentation](https://github.com/RegioneER/rer-linkchecker/tree/main/backend#readme) for the script options and the REST API.

### 2. Frontend

Add the package to the dependencies of your Volto project:

```shell
pnpm add @regioneer/volto-rer-linkchecker
```

Then add it to the add-ons in your `volto.config.js`:

```javascript
const addons = ['@regioneer/volto-rer-linkchecker'];
```

No further configuration is needed.

## Usage

Log in with a user that has the `rer.linkchecker: View report` permission.
By default it is granted to the **Manager**, **Site Administrator** and **Editor** roles.

Open the user menu in the Volto toolbar and choose **Check links**, or go directly to `/controlpanel/linkchecker`.

The page shows the results of the last check run on the backend. To update them, run the check again on the backend: reloading the page is not enough.

## Configuration

The add-on reads only the Volto setting `config.settings.defaultPageSize`, used as the default page size of the report.

## Translations

The interface is available in English and Italian.

## Links

- Source code: <https://github.com/RegioneER/rer-linkchecker>
- Issue tracker: <https://github.com/RegioneER/rer-linkchecker/issues>
- Backend add-on: [`rer.linkchecker`](https://github.com/RegioneER/rer-linkchecker/tree/main/backend)
- Changelog: [CHANGELOG.md](https://github.com/RegioneER/rer-linkchecker/blob/main/frontend/packages/volto-rer-linkchecker/CHANGELOG.md)

## Development

This add-on lives in the [rer-linkchecker](https://github.com/RegioneER/rer-linkchecker) monorepo, together with its backend.
It is developed in isolation with pnpm workspaces and `mrs-developer`.

Prerequisites: [nvm](https://6.docs.plone.org/install/create-project-cookieplone.html#nvm), [Node.js and pnpm](https://6.docs.plone.org/install/create-project.html#node-js), [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make), [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git) and, optionally, [Docker](https://docs.docker.com/get-started/get-docker/).

```shell
git clone git@github.com:RegioneER/rer-linkchecker.git
cd rer-linkchecker/frontend
make install
```

Start the backend, then the frontend in a separate terminal:

```shell
make backend-docker-start
make start
```

Other useful commands (run `make help` for the full list):

| Command | Description |
| --- | --- |
| `make lint` | Run ESLint, Prettier and Stylelint in check mode |
| `make format` | Run ESLint, Prettier and Stylelint in fix mode |
| `make i18n` | Extract the messages to translate into `locales` |
| `make test` | Run the unit tests |

## Credits

Developed with the support of [Regione Emilia-Romagna](https://www.regione.emilia-romagna.it/), which supports the [PloneGov initiative](https://www.plonegov.it/).

This product was developed by the [RedTurtle Technology](https://www.redturtle.it/) team.

## License

This package is licensed under the [MIT license](https://opensource.org/licenses/MIT).
