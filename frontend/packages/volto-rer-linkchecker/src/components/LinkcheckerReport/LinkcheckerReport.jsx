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
  allTypes: {
    id: 'All',
    defaultMessage: 'All',
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
  columnType: {
    id: 'Type',
    defaultMessage: 'Type',
  },
  columnStatus: {
    id: 'Status code',
    defaultMessage: 'Status code',
  },
  columnDescription: {
    id: 'Description',
    defaultMessage: 'Description',
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
    const size =
      value === intl.formatMessage(messages.allTypes) ? itemsTotal : value;
    setPageSize(size);
    setCurrentPage(0);
    fetchReport({ bStart: 0, bSize: size });
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
                <SelectWidget
                  id="link_type"
                  title={intl.formatMessage(messages.linkTypeFilter)}
                  required={false}
                  value={selectedLinkType}
                  onChange={handleLinkTypeChange}
                  choices={[
                    ['INTERNAL', intl.formatMessage(messages.internal)],
                    ['EXTERNAL', intl.formatMessage(messages.external)],
                  ]}
                  wrapped={false}
                />
                <div className="linkchecker-download">
                  <Button
                    primary
                    icon
                    labelPosition="left"
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
                  <Table celled striped className="linkchecker-table">
                    <Table.Header>
                      <Table.Row>
                        <Table.HeaderCell>
                          <FormattedMessage {...messages.columnPage} />
                        </Table.HeaderCell>
                        <Table.HeaderCell>
                          <FormattedMessage {...messages.columnLink} />
                        </Table.HeaderCell>
                        <Table.HeaderCell>
                          <FormattedMessage {...messages.columnType} />
                        </Table.HeaderCell>
                        <Table.HeaderCell>
                          <FormattedMessage {...messages.columnStatus} />
                        </Table.HeaderCell>
                        <Table.HeaderCell>
                          <FormattedMessage {...messages.columnDescription} />
                        </Table.HeaderCell>
                      </Table.Row>
                    </Table.Header>
                    <Table.Body>
                      {items.map((item) => (
                        <Table.Row
                          key={`${item.UID}-${item.link}`}
                          className={`link-type-${item.link_type.toLowerCase()}`}
                        >
                          <Table.Cell>
                            <Link to={flattenToAppURL(item['@id'])}>
                              {item.title}
                            </Link>
                          </Table.Cell>
                          <Table.Cell className="linkchecker-link">
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
                          <Table.Cell>
                            <FormattedMessage
                              {...(item.link_type === 'INTERNAL'
                                ? messages.internal
                                : messages.external)}
                            />
                          </Table.Cell>
                          <Table.Cell className="linkchecker-status">
                            {item.status}
                          </Table.Cell>
                          <Table.Cell>{item.status_description}</Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>

                  <Pagination
                    current={currentPage}
                    total={totalPages(itemsTotal, pageSize)}
                    pageSize={pageSize}
                    pageSizes={[
                      config.settings.defaultPageSize,
                      50,
                      100,
                      intl.formatMessage(messages.allTypes),
                    ]}
                    onChangePage={handlePageChange}
                    onChangePageSize={handlePageSizeChange}
                  />
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
