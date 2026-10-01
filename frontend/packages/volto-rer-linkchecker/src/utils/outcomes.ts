/**
 * What an editor has to do about a link, and which check outcomes call for it.
 *
 * The report speaks http status codes; an editor does not, and a filter
 * offering a dozen of them is a filter nobody uses. The panel asks instead
 * which action to take, and this module is the whole of the mapping: editorial
 * policy, kept on its own so it can be read and tested as such.
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

/**
 * Outcomes nobody can act on without going and looking: the server was too
 * slow, unreachable, refused us, blocked the checker, or answered something
 * that is no verdict on the link itself.
 */
const CHECK_STATUSES = [-1, -3, 400, 401, 403, 405, 429, 500, 503, 521, 526];

/**
 * The statuses to ask the endpoint for, given the action the editor picked.
 *
 * `fix` and `update` are closed lists: each of those outcomes means one thing.
 * `check` is not a list but a remainder — it carries its declared outcomes
 * plus every other one the report happens to hold. The extras are read off the
 * summary, which the endpoint always builds over the *unfiltered* report, so an
 * outcome nobody foresaw (a 502, LinkedIn's 999, whatever a future check
 * returns) is still reachable from a filter instead of sitting in the report
 * with no way to single it out.
 *
 * A known action never returns an empty list, because an empty `status` filter
 * does not mean "nothing matches": it means "no filter", and the panel would
 * answer a request for an empty category with the whole report.
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
 * How many links an action accounts for, out of the same summary.
 *
 * Shown next to each choice, so an editor sees where the work is before
 * clicking: a zero next to "Fix" is the good news the panel exists to deliver.
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
