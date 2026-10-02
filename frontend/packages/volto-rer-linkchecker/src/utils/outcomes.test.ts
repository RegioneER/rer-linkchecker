import { describe, expect, it } from 'vitest';
import {
  ACTION_CHECK,
  ACTION_FIX,
  ACTION_UPDATE,
  ACTIONS,
  countForAction,
  statusesForAction,
} from './outcomes';

// a report holding one outcome per action, plus one nobody classified:
// LinkedIn answers 999, and the next server will invent something else
const summary = [
  { status: 404, status_description: 'Not Found', count: 10 },
  { status: 410, status_description: 'Gone', count: 1 },
  { status: -2, status_description: 'Works over https', count: 4 },
  { status: 403, status_description: 'Blocked', count: 7 },
  { status: 999, status_description: '', count: 2 },
];

describe('statusesForAction', () => {
  it('asks for the outcomes that mean the link is gone', () => {
    expect(statusesForAction(ACTION_FIX, summary)).toEqual([404, 410]);
  });

  it('asks for the one outcome that means the url is out of date', () => {
    expect(statusesForAction(ACTION_UPDATE, summary)).toEqual([-2]);
  });

  it('sweeps an unclassified outcome into "check" rather than losing it', () => {
    const statuses = statusesForAction(ACTION_CHECK, summary);
    expect(statuses).toContain(403);
    expect(statuses).toContain(999);
  });

  it('keeps out of "check" what the other two actions answer for', () => {
    const statuses = statusesForAction(ACTION_CHECK, summary);
    expect(statuses).not.toContain(404);
    expect(statuses).not.toContain(410);
    expect(statuses).not.toContain(-2);
  });

  it('never answers a known action with an empty filter', () => {
    // an empty status list is not "nothing matches", it is "no filter": the
    // endpoint would answer with the whole report
    ACTIONS.forEach((action) => {
      expect(statusesForAction(action, []).length).toBeGreaterThan(0);
    });
  });

  it('filters nothing when no action is picked', () => {
    expect(statusesForAction('', summary)).toEqual([]);
    expect(statusesForAction(null, summary)).toEqual([]);
    expect(statusesForAction(undefined)).toEqual([]);
  });
});

describe('countForAction', () => {
  it('adds up the outcomes the action answers for', () => {
    expect(countForAction(ACTION_FIX, summary)).toBe(11);
    expect(countForAction(ACTION_UPDATE, summary)).toBe(4);
    expect(countForAction(ACTION_CHECK, summary)).toBe(9);
  });

  it('counts every link exactly once, across the three actions', () => {
    const total = ACTIONS.reduce(
      (sum, action) => sum + countForAction(action, summary),
      0,
    );
    expect(total).toBe(summary.reduce((sum, entry) => sum + entry.count, 0));
  });

  it('is zero, not a crash, on a report that has never run', () => {
    expect(countForAction(ACTION_FIX, [])).toBe(0);
    expect(countForAction(ACTION_FIX)).toBe(0);
  });
});
