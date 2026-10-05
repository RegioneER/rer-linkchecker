# Change log

<!-- You should *NOT* be adding new change log entries to this file.
     You should create a file in the news directory instead.
     For helpful instructions, please see:
     https://6.docs.plone.org/contributing/index.html#contributing-change-log-label
-->

<!-- towncrier release notes start -->
## 1.0.0a4 (2026-10-05)

### Backend


#### New features:

- Translate the link status descriptions of the report (`@linkchecker`, `@linkchecker-csv`) in the language of the request, with an italian translation; english stays the default. [#3](https://github.com/RegioneER/rer-linkchecker/issues/3)


#### Bug fixes:

- Give the database connection back while the external links are checked, instead of holding it open for the whole (long) network phase: on RelStorage/PostgreSQL the server closed the idle connection and the run died with "server closed the connection unexpectedly" right before storing its results. [#2](https://github.com/RegioneER/rer-linkchecker/issues/2)



### Frontend

#### Feature

- Rebuild the panel around the action an editor has to take, rather than around http status codes. The filter now offers "to fix", "to update" and "to check" instead of a dozen raw statuses, each with the count of links behind it; "to check" is a remainder rather than a list, so an outcome nobody classified is still reachable from a filter. Every outcome is spelled out in the editor's own language (521 and 526 had no description at all before, the standard http table not knowing them), the columns are named after what they hold — site content, link to check, outcome — and the page says when the list was generated and that the check runs daily. [#3](https://github.com/RegioneER/rer-linkchecker/issue/3)



### Project

No significant changes.




## 1.0.0a3 (2026-09-16)

### Backend

No significant changes.




### Frontend

No significant changes.


### Project

No significant changes.




## 1.0.0a2 (2026-09-15)

### Backend

No significant changes.




### Frontend

No significant changes.


### Project

No significant changes.




## 1.0.0a1 (2026-09-15)

### Backend

No significant changes.




### Frontend

#### Feature

- Add a "Broken links" control panel page that reads the report from the `@linkchecker` endpoint: a filterable, paginated table of the broken links found in site contents, plus a CSV download that honours the active filters. Since the check runs out of band (from cron), the page states when the list was generated and, when it needs refreshing, tells the reader to ask the site managers; a report that has never run is told apart from one that found nothing. [#1](https://github.com/RegioneER/rer-linkchecker/issue/1)

#### Bugfix

- Make the broken links table readable at any width. It now has three columns instead of five — the link type travels with the link as a badge, and the status code carries its description inline — so the link is no longer squeezed into a quarter of the table by the page title. On a phone, where the table stacks into blocks, every cell keeps its own label instead of leaving a stray list of column names at the top, and the pagination wraps rather than pushing the page into a horizontal scroll. The CSV button's icon is lined up with its label. [#2](https://github.com/RegioneER/rer-linkchecker/issue/2)



### Project

No significant changes.




