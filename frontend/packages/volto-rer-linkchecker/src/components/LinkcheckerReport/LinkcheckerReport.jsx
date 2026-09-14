import React, { useCallback, useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { createPortal } from 'react-dom';
import { Link } from 'react-router-dom';
import {
  Button,
  Container,
  Header,
  Loader,
  Message,
  Segment,
  Table,
} from 'semantic-ui-react';
import { useIntl, FormattedMessage, defineMessages } from 'react-intl';
import {
  Helmet,
  expandToBackendURL,
  flattenToAppURL,
} from '@plone/volto/helpers';
import { SelectWidget } from '@plone/volto/components';
import Toolbar from '@plone/volto/components/manage/Toolbar/Toolbar';
import Icon from '@plone/volto/components/theme/Icon/Icon';
import Pagination from '@plone/volto/components/theme/Pagination/Pagination';
import Error from '@plone/volto/components/theme/Error/Error';
import backSVG from '@plone/volto/icons/back.svg';
import downloadSVG from '@plone/volto/icons/download.svg';
import { useClient } from '@plone/volto/hooks';
import config from '@plone/volto/registry';
import { getLinkcheckerReport } from '../../actions/linkchecker';
import {
  buildQueryString,
  formatLastUpdate,
  pageToBStart,
  totalPages,
} from '../../utils/query';
import './LinkcheckerReport.css';

const messages = defineMessages({
  pageTitle: {
    id: 'Broken links',
    defaultMessage: 'Broken links',
  },
  pageDescription: {
    id: 'The links found in site contents that could not be reached',
    defaultMessage:
      'The links found in site contents that could not be reached',
  },
  generatedOn: {
    id: 'This list was generated on {date} and took {duration} seconds',
    defaultMessage:
      'This list was generated on {date} and took {duration} seconds',
  },
  generatedOnShort: {
    id: 'This list was generated on {date}',
    defaultMessage: 'This list was generated on {date}',
  },
  askManagers: {
    id: 'The check runs periodically: to have the list updated, ask the site managers',
    defaultMessage:
      'The check runs periodically: to have the list updated, ask the site managers',
  },
  neverRunTitle: {
    id: 'No check has run yet',
    defaultMessage: 'No check has run yet',
  },
  neverRunBody: {
    id: 'There is no report to show. Ask the site managers to run the link check',
    defaultMessage:
      'There is no report to show. Ask the site managers to run the link check',
  },
  nothingBroken: {
    id: 'No broken links were found',
    defaultMessage: 'No broken links were found',
  },
  noResultsForFilters: {
    id: 'No broken links match the current filters',
    defaultMessage: 'No broken links match the current filters',
  },
  statusFilter: {
    id: 'Status',
    defaultMessage: 'Status',
  },
  linkTypeFilter: {
    id: 'Link type',
    defaultMessage: 'Link type',
  },
  internal: {
    id: 'Internal',
    defaultMessage: 'Internal',
  },
  external: {
    id: 'External',
    defaultMessage: 'External',
  },
  downloadCsv: {
    id: 'Download CSV',
    defaultMessage: 'Download CSV',
  },
  downloadFailed: {
    id: 'The download failed. Try again',
    defaultMessage: 'The download failed. Try again',
  },
  columnPage: {
    id: 'Page',
    defaultMessage: 'Page',
  },
  columnLink: {
    id: 'Link',
    defaultMessage: 'Link',
  },
  // Heads the cell that carries both the code and its description: the code is
  // the datum, the description only spells it out, so one column answers for
  // both. See the table below for why they are not two columns any more.
  columnStatus: {
    id: 'Status code',
    defaultMessage: 'Status code',
  },
  results: {
    id: 'Results',
    defaultMessage: 'Results',
  },
  loading: {
    id: 'Loading',
    defaultMessage: 'Loading...',
  },
  backToControlPanel: {
    id: 'Back to Control Panel',
    defaultMessage: 'Back to Control Panel',
  },
});

const CSV_FALLBACK_FILENAME = 'broken_links.csv';

/**
 * Pull the file name out of the Content-Disposition the backend sets, so the
 * downloaded file keeps the date of the data it contains.
 */
export const filenameFromDisposition = (disposition) => {
  const match = /filename="?([^";]+)"?/.exec(disposition || '');
  return match ? match[1] : CSV_FALLBACK_FILENAME;
};

const LinkcheckerReport = (props) => {
  const dispatch = useDispatch();
  const isClient = useClient();
  const intl = useIntl();
  const pathname = props.location?.pathname || '/controlpanel/linkchecker';

  const [selectedStatuses, setSelectedStatuses] = useState([]);
  const [selectedLinkType, setSelectedLinkType] = useState('');
  const [currentPage, setCurrentPage] = useState(0);
  const [pageSize, setPageSize] = useState(config.settings.defaultPageSize);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);

  const {
    items,
    items_total: itemsTotal,
    summary,
    last_update: lastUpdate,
    duration,
    loading,
    loaded,
    error,
  } = useSelector((state) => state.linkchecker);
  // the csv download cannot go through the redux pipeline: it needs the raw
  // bytes, and plone.restapi only accepts the token in the Authorization header
  const token = useSelector((state) => state.userSession?.token);

  const fetchReport = useCallback(
    (overrides = {}) => {
      const query = {
        status: selectedStatuses,
        linkType: selectedLinkType,
        bStart: pageToBStart(currentPage, pageSize),
        bSize: pageSize,
        ...overrides,
      };
      dispatch(getLinkcheckerReport(query));
    },
    [dispatch, selectedStatuses, selectedLinkType, currentPage, pageSize],
  );

  useEffect(() => {
    dispatch(getLinkcheckerReport({ bSize: config.settings.defaultPageSize }));
  }, [dispatch]);

  const handleStatusChange = (id, value) => {
    const statuses = value || [];
    setSelectedStatuses(statuses);
    setCurrentPage(0);
    fetchReport({ status: statuses, bStart: 0 });
  };

  const handleLinkTypeChange = (id, value) => {
    const linkType = value || '';
    setSelectedLinkType(linkType);
    setCurrentPage(0);
    fetchReport({ linkType, bStart: 0 });
  };

  const handlePageChange = (event, { value }) => {
    setCurrentPage(value);
    fetchReport({ bStart: pageToBStart(value, pageSize) });
  };

  const handlePageSizeChange = (event, { value }) => {
    setPageSize(value);
    setCurrentPage(0);
    fetchReport({ bStart: 0, bSize: value });
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(false);
    let objectUrl;
    try {
      // same filters as the table: whoever narrows the report down and then
      // downloads expects to get what they are looking at
      const queryString = buildQueryString({
        status: selectedStatuses,
        linkType: selectedLinkType,
      });
      const url = expandToBackendURL(
        `/@linkchecker-csv${queryString ? `?${queryString}` : ''}`,
      );
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`Download failed with status ${response.status}`);
      }
      const filename = filenameFromDisposition(
        response.headers.get('Content-Disposition'),
      );
      const blob = await response.blob();
      objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (exception) {
      setDownloadError(true);
    } finally {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
      setDownloading(false);
    }
  };

  if (error) {
    return <Error error={error} />;
  }

  const neverChecked = loaded && lastUpdate === null;
  const formattedDate = formatLastUpdate(lastUpdate, intl.locale);
  const hasFilters = selectedStatuses.length > 0 || Boolean(selectedLinkType);

  const statusChoices = (summary || []).map((entry) => [
    String(entry.status),
    `${entry.status_description} (${entry.count})`,
  ]);

  return (
    <Container className="view-wrapper controlpanel-linkchecker cms-ui">
      <Helmet title={intl.formatMessage(messages.pageTitle)} />
      <Segment.Group raised>
        <Segment className="primary">
          <Header as="h1">
            <FormattedMessage {...messages.pageTitle} />
          </Header>
          <p>
            <FormattedMessage {...messages.pageDescription} />
          </p>
        </Segment>

        <Segment>
          {neverChecked ? (
            <Message warning>
              <Message.Header>
                <FormattedMessage {...messages.neverRunTitle} />
              </Message.Header>
              <p>
                <FormattedMessage {...messages.neverRunBody} />
              </p>
            </Message>
          ) : (
            <Message info className="linkchecker-generated-on">
              <p>
                {duration ? (
                  <FormattedMessage
                    {...messages.generatedOn}
                    values={{
                      date: formattedDate,
                      duration: Math.round(duration),
                    }}
                  />
                ) : (
                  <FormattedMessage
                    {...messages.generatedOnShort}
                    values={{ date: formattedDate }}
                  />
                )}
              </p>
              <p>
                <FormattedMessage {...messages.askManagers} />
              </p>
            </Message>
          )}
        </Segment>

        {!neverChecked && (
          <>
            <Segment>
              <div className="linkchecker-controls ui form">
                {/* wrapped={false} drops the whole FormFieldWrapper, label
                    included, so each filter carries its own: without it the
                    two dropdowns show a bare "Select…" and the reader cannot
                    tell which one filters what. The widget is nested in the
                    label rather than pointed at with htmlFor, because
                    react-select puts the id it is given on the container div
                    and generates the input's own id, which SelectWidget does
                    not let us set: an htmlFor would name a div. The accessible
                    name comes from the aria-label SelectWidget builds out of
                    `title`. */}
                <label className="linkchecker-filter">
                  <span className="linkchecker-filter-label">
                    <FormattedMessage {...messages.statusFilter} />
                  </span>
                  <SelectWidget
                    id="status"
                    title={intl.formatMessage(messages.statusFilter)}
                    required={false}
                    isMulti
                    value={selectedStatuses}
                    onChange={handleStatusChange}
                    choices={statusChoices}
                    wrapped={false}
                  />
                </label>
                <label className="linkchecker-filter">
                  <span className="linkchecker-filter-label">
                    <FormattedMessage {...messages.linkTypeFilter} />
                  </span>
                  {/* isClearable so the filter can be removed: without it
                      react-select shows no reset, and there is no "all" choice
                      to go back to. Deliberately not set on the multi select
                      above: its clear-all hands SelectWidget a null that its
                      onChange maps over unguarded, and each value can be
                      removed by its own chip anyway. */}
                  <SelectWidget
                    id="link_type"
                    title={intl.formatMessage(messages.linkTypeFilter)}
                    required={false}
                    isClearable
                    value={selectedLinkType}
                    onChange={handleLinkTypeChange}
                    choices={[
                      ['INTERNAL', intl.formatMessage(messages.internal)],
                      ['EXTERNAL', intl.formatMessage(messages.external)],
                    ]}
                    wrapped={false}
                  />
                </label>
                <div className="linkchecker-download">
                  {/* No `icon labelPosition="left"`: that lays the icon out as
                      an absolutely positioned box of its own, sized for an icon
                      font, and Volto's Icon is an inline svg carrying its own
                      width and height — it came out hanging off the top of the
                      button. A plain button lines the two up with flex, in the
                      css. */}
                  <Button
                    primary
                    className="linkchecker-download-button"
                    loading={downloading}
                    disabled={downloading || itemsTotal === 0}
                    onClick={handleDownload}
                  >
                    <Icon name={downloadSVG} size="20px" />
                    <FormattedMessage {...messages.downloadCsv} />
                  </Button>
                </div>
              </div>
              {downloadError && (
                <Message error>
                  <FormattedMessage {...messages.downloadFailed} />
                </Message>
              )}
            </Segment>

            <Segment>
              {loading && (
                <Loader active inline="centered" size="medium">
                  <FormattedMessage {...messages.loading} />
                </Loader>
              )}

              {!loading && items.length === 0 && (
                <p>
                  <FormattedMessage
                    {...(hasFilters
                      ? messages.noResultsForFilters
                      : messages.nothingBroken)}
                  />
                </p>
              )}

              {!loading && items.length > 0 && (
                <>
                  <Header as="h2">
                    <FormattedMessage {...messages.results} /> ({itemsTotal})
                  </Header>
                  {/* Three columns, not five. The link is what the reader is
                      here for, and with five columns it got a quarter of the
                      table while the page title took half of it. The two that
                      went away were not carrying a column's worth of meaning:
                      the type is an attribute of the link, and the status
                      description is the status code spelled out.
                      Every cell names its own column in `data-label`, which is
                      what the stacked layout shows below the mobile breakpoint,
                      where a table header cannot follow the values. */}
                  <Table celled striped className="linkchecker-table">
                    <Table.Header>
                      <Table.Row>
                        <Table.HeaderCell className="linkchecker-col-page">
                          <FormattedMessage {...messages.columnPage} />
                        </Table.HeaderCell>
                        <Table.HeaderCell className="linkchecker-col-link">
                          <FormattedMessage {...messages.columnLink} />
                        </Table.HeaderCell>
                        <Table.HeaderCell className="linkchecker-col-status">
                          <FormattedMessage {...messages.columnStatus} />
                        </Table.HeaderCell>
                      </Table.Row>
                    </Table.Header>
                    <Table.Body>
                      {items.map((item) => (
                        <Table.Row
                          key={`${item.UID}-${item.link}`}
                          className={`link-type-${item.link_type.toLowerCase()}`}
                        >
                          <Table.Cell
                            data-label={intl.formatMessage(messages.columnPage)}
                          >
                            <Link to={flattenToAppURL(item['@id'])}>
                              {item.title}
                            </Link>
                          </Table.Cell>
                          <Table.Cell
                            className="linkchecker-link"
                            data-label={intl.formatMessage(messages.columnLink)}
                          >
                            <span
                              className={`linkchecker-type ${
                                item.link_type === 'INTERNAL'
                                  ? 'is-internal'
                                  : 'is-external'
                              }`}
                            >
                              <FormattedMessage
                                {...(item.link_type === 'INTERNAL'
                                  ? messages.internal
                                  : messages.external)}
                              />
                            </span>
                            {item.link_type === 'EXTERNAL' ? (
                              <a
                                href={item.link}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {item.link}
                              </a>
                            ) : (
                              item.link
                            )}
                          </Table.Cell>
                          <Table.Cell
                            className="linkchecker-status"
                            data-label={intl.formatMessage(
                              messages.columnStatus,
                            )}
                          >
                            <span className="linkchecker-status-code">
                              {item.status}
                            </span>
                            {item.status_description && (
                              <span className="linkchecker-status-description">
                                {/* the leading space is a real space, not a
                                    margin: it is the only place the line is
                                    allowed to break, and without it "401" and
                                    its description are one unbreakable token
                                    that overflows the cell */}
                                {` ${item.status_description}`}
                              </span>
                            )}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>

                  {/* Pagination renders its "Show:" menu whenever pageSize is
                      set, however few the pages, so a report that fits in one
                      page is not paginated at all. Measured against the
                      default size rather than the current one, so raising the
                      size never hides the control that lowers it again. */}
                  {itemsTotal > config.settings.defaultPageSize && (
                    <Pagination
                      current={currentPage}
                      total={totalPages(itemsTotal, pageSize)}
                      pageSize={pageSize}
                      pageSizes={[config.settings.defaultPageSize, 50, 100]}
                      onChangePage={handlePageChange}
                      onChangePageSize={handlePageSizeChange}
                    />
                  )}
                </>
              )}
            </Segment>
          </>
        )}
      </Segment.Group>

      {isClient &&
        createPortal(
          <Toolbar
            pathname={pathname}
            hideDefaultViewButtons
            inner={
              <Link to="/controlpanel" className="item">
                <Icon
                  name={backSVG}
                  className="contents circled"
                  size="30px"
                  title={intl.formatMessage(messages.backToControlPanel)}
                />
              </Link>
            }
          />,
          document.getElementById('toolbar'),
        )}
    </Container>
  );
};

export default LinkcheckerReport;
