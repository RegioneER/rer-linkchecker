# Changelog

<!--
   You should *NOT* be adding new change log entries to this file.
   You should create a file in the news directory instead.
   For helpful instructions, please see:
   https://github.com/plone/plone.releaser/blob/master/ADD-A-NEWS-ITEM.rst
-->

<!-- towncrier release notes start -->

## 1.0.0a4 (2026-10-05)


### New features:

- Translate the link status descriptions of the report (`@linkchecker`, `@linkchecker-csv`) in the language of the request, with an italian translation; english stays the default. [#3](https://github.com/RegioneER/rer-linkchecker/issues/3)


### Bug fixes:

- Give the database connection back while the external links are checked, instead of holding it open for the whole (long) network phase: on RelStorage/PostgreSQL the server closed the idle connection and the run died with "server closed the connection unexpectedly" right before storing its results. [#2](https://github.com/RegioneER/rer-linkchecker/issues/2)

## 1.0.0a3 (2026-09-16)

No significant changes.


## 1.0.0a2 (2026-09-15)

No significant changes.


## 1.0.0a1 (2026-09-15)

No significant changes.
