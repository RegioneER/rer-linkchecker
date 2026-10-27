# Changelog

<!--
   You should *NOT* be adding new change log entries to this file.
   You should create a file in the news directory instead.
   For helpful instructions, please see:
   https://github.com/plone/plone.releaser/blob/master/ADD-A-NEWS-ITEM.rst
-->

<!-- towncrier release notes start -->

## 1.1.0 (2026-10-27)


### New features:

- Accept patterns in `RER_LINKCHECKER_BLACKLIST_DOMAINS`: `*-iam.regione.emilia-romagna.it` blacklists the editorial domain of every site at once. The blacklist now also wins over the domain the check runs on, so absolute links to a blacklisted editorial domain are reported even when the check runs from it. 


### Bug fixes:

- Give up on a host after consecutive connection errors only, no longer after timeouts: a timeout means the server accepted the connection and that page was slow, which tells nothing about the next one. On ambiente, `applicazioni.regione.emilia-romagna.it` was given up on after three slow pages in a row, and 28 of its working links were reported as timeouts. 

## 1.1.0a0 (2026-10-26)


### New features:

- Give up on a host after 3 consecutive timeouts or connection errors: its remaining links get the same outcome without being fetched, and are tried again at the next run. A single dead host with tens of links no longer keeps two workers busy for minutes. Tune it with `check_site(host_max_failures=...)` or `check_broken_links --host-max-failures`, `0` to never give up. 
- Report the links to a blacklisted domain, i.e. a domain contents must never link to (e.g. the editorial backend of the sites), as `-4` "Domain not allowed in contents", among the links to fix and without fetching them. The domains, which cover their subdomains too, are read from the `RER_LINKCHECKER_BLACKLIST_DOMAINS` environment variable, comma separated. 
- Wait at most 5 seconds to open a connection, apart from the 15 allowed to answer: an unreachable host is found out in a third of the time, and reported as a connection error rather than a timeout. Tune it with `check_site(connect_timeout=...)` or `check_broken_links --connect-timeout`. 


### Bug fixes:

- Report a link whose host cannot be parsed (e.g. a label longer than 63 characters, typical of a url glued to the following markup) as a connection error, instead of crashing the whole check with an unhandled urllib3 `LocationParseError`. 
- Stop extracting the markup or the punctuation that follows a url as part of the link: a url that is also the text of its own link (`https://a.it</a></span></p>`) or that ends a sentence (`https://a.it.`, `(https://a.it),`) was checked as written and reported as broken. 

## 1.0.1 (2026-10-21)

No significant changes.


## 1.0.0 (2026-10-20)

No significant changes.


## 1.0.0a8 (2026-10-07)


### New features:

- Each item of `@linkchecker` carries the `action` an editor has to take on the link: `fix` (404, 410), `update` (-2) or `check` (any other outcome), so a client no longer has to repeat the mapping. 

## 1.0.0a7 (2026-10-05)

No significant changes.


## 1.0.0a6 (2026-10-05)

No significant changes.


## 1.0.0a5 (2026-10-05)


### New features:

- Give the csv report (`@linkchecker-csv`, and the file the `check_broken_links` script writes) the columns and labels of the panel: site content, link to check, link type, outcome, outcome description, translated in the language of the request like the descriptions already were. A new column tells the action to take on each link: to fix, to update or to check. The header names change accordingly: whoever reads the csv by column name (`PAGE`, `STATUS`, ...) has to follow. 

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
