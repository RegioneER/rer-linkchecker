/**
 * Query building for the @linkchecker endpoints.
 *
 * Kept apart from the component so the filter and paging rules can be tested
 * without a DOM or a redux store.
 */

export type ReportQuery = {
  /** statuses to keep; the endpoint takes the parameter repeated */
  status?: Array<string | number> | null;
  /** 'INTERNAL' | 'EXTERNAL', or empty for both */
  linkType?: string | null;
  bStart?: number;
  bSize?: number;
};

export type ReportParams = {
  status?: string[];
  type?: string;
  b_start?: number;
  b_size?: number;
};

/**
 * Filters and paging as a params object.
 *
 * Empty filters are left out rather than sent empty, so the request stays the
 * plain "give me everything" one the endpoint answers fastest. `status` stays
 * an array: superagent serializes arrays as a repeated key, which is the shape
 * the endpoint expects.
 */
export function buildParams({
  status,
  linkType,
  bStart,
  bSize,
}: ReportQuery = {}): ReportParams {
  const params: ReportParams = {};
  const statuses = (status ?? [])
    .filter((value) => value !== null && value !== undefined && value !== '')
    .map(String);
  if (statuses.length) {
    params.status = statuses;
  }
  if (linkType) {
    params.type = linkType;
  }
  if (bStart) {
    // omitted when 0: the endpoint already starts from the beginning
    params.b_start = bStart;
  }
  if (bSize) {
    params.b_size = bSize;
  }
  return params;
}

/**
 * The same filters as a query string, for the csv download.
 *
 * The download cannot go through the redux/superagent pipeline (it needs the
 * raw bytes and an Authorization header), so it builds its own URL from the
 * very same params, and whoever downloads gets exactly the rows they filtered.
 */
export function buildQueryString(query: ReportQuery = {}): string {
  const params = buildParams(query);
  const search = new URLSearchParams();
  (params.status ?? []).forEach((value) => search.append('status', value));
  if (params.type) {
    search.append('type', params.type);
  }
  if (params.b_start) {
    search.append('b_start', String(params.b_start));
  }
  if (params.b_size) {
    search.append('b_size', String(params.b_size));
  }
  return search.toString();
}

/** Zero-based page index -> the b_start the endpoint wants. */
export function pageToBStart(page: number, pageSize: number): number {
  return Math.max(0, page) * pageSize;
}

/** Total number of pages for a result set, at least 1 so paging never breaks. */
export function totalPages(itemsTotal: number, pageSize: number): number {
  if (!pageSize) {
    return 1;
  }
  return Math.max(1, Math.ceil(itemsTotal / pageSize));
}

/**
 * The report is generated out of band, so its age is shown to the reader.
 * Formatted in the user's locale: an ISO string is not what a reader wants.
 * Returns null when no check has ever run, which the caller must tell apart
 * from "the last check found nothing".
 */
export function formatLastUpdate(
  isoDate: string | null | undefined,
  locale?: string,
): string | null {
  if (!isoDate) {
    return null;
  }
  const date = new Date(isoDate);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleString(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}
