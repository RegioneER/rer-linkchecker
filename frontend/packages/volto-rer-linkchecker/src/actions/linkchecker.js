import { GET_LINKCHECKER_REPORT } from '../constants/ActionTypes';
import { buildParams } from '../utils/query';

/**
 * Read the stored broken links report.
 *
 * The endpoint never runs a check: it serves what the last run (a cron job)
 * left behind, so this is always cheap no matter how big the site is.
 *
 * @param {Object} options status, linkType, bStart, bSize - see buildParams
 */
export function getLinkcheckerReport(options = {}) {
  return {
    type: GET_LINKCHECKER_REPORT,
    request: {
      op: 'get',
      path: '/@linkchecker',
      params: buildParams(options),
    },
  };
}
