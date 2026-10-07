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
import {
  ACTION_CHECK,
  ACTION_FIX,
  ACTION_UPDATE,
  ACTIONS,
  countForAction,
  statusesForAction,
} from '../../utils/outcomes';
import './LinkcheckerReport.css';

const messages = defineMessages({
  pageTitle: {
    id: 'Site link check',
    defaultMessage: 'Site link check',
  },
  intro: {
    id: 'The list shows the site links, internal and external, that the daily automatic check found to be fixed, updated or looked at',
    defaultMessage:
      'The list shows the site links, internal and external, that the daily automatic check found to be fixed, updated or looked at.',
  },
  introFilter: {
    id: 'In the {field} field you can filter the list by the action to take:',
    defaultMessage:
      'In the {field} field you can filter the list by the action to take:',
  },
  generatedOn: {
    id: 'This list was generated on {date} at {time}. The check runs automatically every day and the list is updated accordingly',
    defaultMessage:
      'This list was generated on {date} at {time}. The check runs automatically every day and the list is updated accordingly.',
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
  // The intro quotes this very message, and the table heads its action column
  // with it, so a rename carries over to everything that points at the field.
  actionFilter: {
    id: 'Link actions',
    defaultMessage: 'Link actions',
  },
  // "To fix" rather than "Fix": these msgids land in the project-wide
  // catalogue, where a bare "Update" would collide with Volto's own.
  actionFix: {
    id: 'To fix',
    defaultMessage: 'To fix',
  },
  actionUpdate: {
    id: 'To update',
    defaultMessage: 'To update',
  },
  actionCheck: {
    id: 'To check',
    defaultMessage: 'To check',
  },
  actionFixHelp: {
    id: 'shows the links that lead to resources that are not available (broken links). Fix them by removing or replacing them',
    defaultMessage:
      'shows the links that lead to resources that are not available (broken links). Fix them by removing or replacing them.',
  },
  actionUpdateHelp: {
    id: 'shows reachable links that point to HTTP instead of HTTPS. Edit the url, replacing http with HTTPS',
    defaultMessage:
      'shows reachable links that point to HTTP instead of HTTPS. Edit the url, replacing http with HTTPS.',
  },
  actionCheckHelp: {
    id: 'shows the links the system could not verify. Check them by hand to see whether they work and whether they need fixing',
    defaultMessage:
      'shows the links the system could not verify. Check them by hand to see whether they work and whether they need fixing.',
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
    id: 'Site content',
    defaultMessage: 'Site content',
  },
  columnLink: {
    id: 'Link to check',
    defaultMessage: 'Link to check',
  },
  // One column for code and description: the second only spells out the first.
  columnStatus: {
    id: 'Outcome',
    defaultMessage: 'Outcome',
  },
  results: {
    id: 'Results',
    defaultMessage: 'Results',
  },
  loading: {
    id: 'Loading',
    defaultMessage: 'Loading...',
  },
  backToHome: {
    id: 'Home',
    defaultMessage: 'Home',
  },
});

/**
 * What each outcome means, in words an editor can act on. The backend only has
 * the standard http reason phrase, in english, and nothing at all for the
 * codes outside that table: 521 and 526 arrive with an empty description.
 * Keyed by status code; anything unlisted falls back to what the backend sent.
 */
const outcomes = defineMessages({
  '-1': {
    id: 'Response too slow (timeout)',
    defaultMessage: 'Response too slow (timeout)',
  },
  '-2': {
    id: 'Link to update to HTTPS',
    defaultMessage: 'Link to update to HTTPS',
  },
  '-3': {
    id: 'Connection error',
    defaultMessage: 'Connection error',
  },
  400: {
    id: 'Invalid request',
    defaultMessage: 'Invalid request',
  },
  401: {
    id: 'Access not authorized',
    defaultMessage: 'Access not authorized',
  },
  403: {
    id: 'Request blocked',
    defaultMessage: 'Request blocked',
  },
  404: {
    id: 'Resource not found',
    defaultMessage: 'Resource not found',
  },
  405: {
    id: 'Check method not allowed',
    defaultMessage: 'Check method not allowed',
  },
  410: {
    id: 'Resource removed',
    defaultMessage: 'Resource removed',
  },
  429: {
    id: 'Check blocked by too many requests',
    defaultMessage: 'Check blocked by too many requests',
  },
  500: {
    id: 'Error on the target server',
    defaultMessage: 'Error on the target server',
  },
  503: {
    id: 'Service temporarily unavailable',
    defaultMessage: 'Service temporarily unavailable',
  },
  521: {
    id: 'Target server unreachable',
    defaultMessage: 'Target server unreachable',
  },
  526: {
    id: 'Invalid security certificate',
    defaultMessage: 'Invalid security certificate',
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

/**
 * Ours when we have words for that code, the backend's otherwise. Empty when
 * neither has any, which is how the cell avoids a dangling dash.
 */
const outcomeText = (intl, item) =>
  outcomes[item.status]
    ? intl.formatMessage(outcomes[item.status])
    : item.status_description;

const LinkcheckerReport = (props) => {
  const dispatch = useDispatch();
  const isClient = useClient();
  const intl = useIntl();
  const pathname = props.location?.pathname || '/controlpanel/linkchecker';

  const [selectedAction, setSelectedAction] = useState('');
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
    loading,
    loaded,
    error,
  } = useSelector((state) => state.linkchecker);
  // the csv download cannot go through the redux pipeline: it needs the raw
  // bytes, and plone.restapi only accepts the token in the Authorization header
  const token = useSelector((state) => state.userSession?.token);

  // The endpoint filters by status, the panel by action. `action` is its own
  // override because the handler knows it before the state does.
  const fetchReport = useCallback(
    (overrides = {}) => {
      const { action = selectedAction, ...rest } = overrides;
      dispatch(
        getLinkcheckerReport({
          status: statusesForAction(action, summary),
          linkType: selectedLinkType,
          bStart: pageToBStart(currentPage, pageSize),
          bSize: pageSize,
          ...rest,
        }),
      );
    },
    [
      dispatch,
      selectedAction,
      selectedLinkType,
      currentPage,
      pageSize,
      summary,
    ],
  );

  useEffect(() => {
    dispatch(getLinkcheckerReport({ bSize: config.settings.defaultPageSize }));
  }, [dispatch]);

  const handleActionChange = (id, value) => {
    const action = value || '';
    setSelectedAction(action);
    setCurrentPage(0);
    fetchReport({ action, bStart: 0 });
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
        status: statusesForAction(selectedAction, summary),
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
  const generatedAt = formatLastUpdate(lastUpdate, intl.locale);
  const hasFilters = Boolean(selectedAction) || Boolean(selectedLinkType);

  const actionLabels = {
    [ACTION_FIX]: messages.actionFix,
    [ACTION_UPDATE]: messages.actionUpdate,
    [ACTION_CHECK]: messages.actionCheck,
  };
  const actionHelp = {
    [ACTION_FIX]: messages.actionFixHelp,
    [ACTION_UPDATE]: messages.actionUpdateHelp,
    [ACTION_CHECK]: messages.actionCheckHelp,
  };
  // the count says where the work is before anything is clicked
  const actionChoices = ACTIONS.map((action) => [
    action,
    `${intl.formatMessage(actionLabels[action])} (${countForAction(
      action,
      summary,
    )})`,
  ]);

  return (
    <Container className="view-wrapper controlpanel-linkchecker cms-ui">
      <Helmet title={intl.formatMessage(messages.pageTitle)} />
      <Segment.Group raised>
        <Segment className="primary">
          <Header as="h1">
            <FormattedMessage {...messages.pageTitle} />
          </Header>
          {/* one class for the whole intro: the banner styles its contents as
              a heading, and this is a description */}
          <div className="linkchecker-intro">
            <p>
              <FormattedMessage {...messages.intro} />
            </p>
            {/* a value, not a rich-text tag: the tag syntax changed across
                react-intl majors, and this addon is built against more than
                one */}
            <p>
              <FormattedMessage
                {...messages.introFilter}
                values={{
                  field: (
                    <strong>
                      <FormattedMessage {...messages.actionFilter} />
                    </strong>
                  ),
                }}
              />
            </p>
            <ul className="linkchecker-actions-legend">
              {ACTIONS.map((action) => (
                <li key={action}>
                  <strong>
                    <FormattedMessage {...actionLabels[action]} />
                  </strong>
                  {': '}
                  <FormattedMessage {...actionHelp[action]} />
                </li>
              ))}
            </ul>
          </div>
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
                <FormattedMessage
                  {...messages.generatedOn}
                  values={{ date: generatedAt?.date, time: generatedAt?.time }}
                />
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
                    <FormattedMessage {...messages.actionFilter} />
                  </span>
                  {/* one at a time: the three are a workflow, not tags.
                      isClearable is the way back to the whole report. */}
                  <SelectWidget
                    id="link_action"
                    title={intl.formatMessage(messages.actionFilter)}
                    required={false}
                    isClearable
                    value={selectedAction}
                    onChange={handleActionChange}
                    choices={actionChoices}
                    wrapped={false}
                  />
                </label>
                <label className="linkchecker-filter">
                  <span className="linkchecker-filter-label">
                    <FormattedMessage {...messages.linkTypeFilter} />
                  </span>
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
                  {/* no `icon labelPosition="left"`: it positions the icon
                      absolutely, in a box sized for an icon font, and Volto's
                      inline svg hung off the top. Flex instead, in the css. */}
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
                  {/* Four columns, not six: the type belongs to the link and
                      the description to the code. The action is a column of its
                      own, because the whole report, unfiltered, mixes all three.
                      Each cell names its column in `data-label`, which is what
                      the stacked layout shows on a phone, where the header
                      cannot follow the values. */}
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
                        <Table.HeaderCell className="linkchecker-col-action">
                          <FormattedMessage {...messages.actionFilter} />
                        </Table.HeaderCell>
                      </Table.Row>
                    </Table.Header>
                    <Table.Body>
                      {items.map((item) => {
                        const outcome = outcomeText(intl, item);
                        return (
                          <Table.Row
                            key={`${item.UID}-${item.link}`}
                            className={`link-type-${item.link_type.toLowerCase()}`}
                          >
                            <Table.Cell
                              data-label={intl.formatMessage(
                                messages.columnPage,
                              )}
                            >
                              <Link to={flattenToAppURL(item['@id'])}>
                                {item.title}
                              </Link>
                            </Table.Cell>
                            <Table.Cell
                              className="linkchecker-link"
                              data-label={intl.formatMessage(
                                messages.columnLink,
                              )}
                            >
                              {/* the css tells the two apart through the row's
                                own link-type class, set above */}
                              <span className="linkchecker-type">
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
                              {outcome && (
                                <span className="linkchecker-status-description">
                                  {/* a real space, not a margin: it is the only
                                    place the line may break, and without it the
                                    cell overflows */}
                                  {` – ${outcome}`}
                                </span>
                              )}
                            </Table.Cell>
                            <Table.Cell
                              className="linkchecker-action"
                              data-label={intl.formatMessage(
                                messages.actionFilter,
                              )}
                            >
                              {/* the backend decides: an unclassified outcome
                                  comes already filed under "check" */}
                              {actionLabels[item.action] && (
                                <FormattedMessage
                                  {...actionLabels[item.action]}
                                />
                              )}
                            </Table.Cell>
                          </Table.Row>
                        );
                      })}
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
              <Link to="/" className="item">
                <Icon
                  name={backSVG}
                  className="contents circled"
                  size="30px"
                  title={intl.formatMessage(messages.backToHome)}
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
