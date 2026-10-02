/**
 * What an editor has to do about a link, and which outcomes call for it.
 *
 * The report speaks http status codes, an editor does not: the panel asks
 * which action to take, and this is the whole of the mapping.
 */

export const ACTION_FIX = 'fix';
export const ACTION_UPDATE = 'update';
export const ACTION_CHECK = 'check';

/** The actions, in the order the panel offers them. */
export const ACTIONS = [ACTION_FIX, ACTION_UPDATE, ACTION_CHECK];

/** One entry per status present in the report, as the endpoint sends it. */
export type SummaryEntry = {
  status: number | string;
  status_description?: string;
  count: number;
};

/** Gone: the link has to be removed or replaced. */
const FIX_STATUSES = [404, 410];

/** Reachable over https, so only the url is out of date. */
const UPDATE_STATUSES = [-2];

/** Nothing an editor can act on without going and looking. */
const CHECK_STATUSES = [-1, -3, 400, 401, 403, 405, 429, 500, 503, 521, 526];

/**
 * The statuses to ask the endpoint for, given the action picked.
 *
 * `check` is a remainder, not a list: its declared outcomes plus anything else
 * the report holds, read off the summary (which the endpoint builds over the
 * unfiltered report), so a 502 or LinkedIn's 999 stays reachable.
 *
 * Never empty for a known action: an empty `status` means "no filter", and the
 * panel would answer an empty category with the whole report.
 */
export function statusesForAction(
  action: string | null | undefined,
  summary: SummaryEntry[] = [],
): number[] {
  switch (action) {
    case ACTION_FIX:
      return [...FIX_STATUSES];
    case ACTION_UPDATE:
      return [...UPDATE_STATUSES];
    case ACTION_CHECK: {
      const extras = (summary || [])
        .map((entry) => Number(entry.status))
        .filter(
          (status) =>
            Number.isFinite(status) &&
            !FIX_STATUSES.includes(status) &&
            !UPDATE_STATUSES.includes(status) &&
            !CHECK_STATUSES.includes(status),
        );
      return [...CHECK_STATUSES, ...new Set(extras)];
    }
    default:
      // nothing picked: no filter at all, which is the whole report
      return [];
  }
}

/**
 * How many links an action accounts for. Shown next to each choice: a zero
 * next to "to fix" is good news, worth seeing before clicking.
 */
export function countForAction(
  action: string | null | undefined,
  summary: SummaryEntry[] = [],
): number {
  const wanted = new Set(statusesForAction(action, summary));
  return (summary || []).reduce(
    (total, entry) =>
      wanted.has(Number(entry.status)) ? total + (entry.count || 0) : total,
    0,
  );
}
