import { describe, expect, it } from 'vitest';
import {
  buildParams,
  buildQueryString,
  formatLastUpdate,
  pageToBStart,
  totalPages,
} from './query';

describe('buildParams', () => {
  it('leaves empty filters out instead of sending them empty', () => {
    expect(buildParams()).toEqual({});
    expect(buildParams({ status: [], linkType: '', bStart: 0 })).toEqual({});
  });

  it('keeps status an array, so it is sent as a repeated parameter', () => {
    // the endpoint reads ?status=404&status=-2, and superagent serializes an
    // array exactly that way
    expect(buildParams({ status: [404, -2] }).status).toEqual(['404', '-2']);
  });

  it('coerces status values coming from the select widget', () => {
    expect(buildParams({ status: ['404'] }).status).toEqual(['404']);
  });

  it('drops empty entries a cleared select leaves behind', () => {
    expect(buildParams({ status: ['404', '', null] }).status).toEqual(['404']);
  });

  it('maps linkType onto the type parameter', () => {
    expect(buildParams({ linkType: 'EXTERNAL' })).toEqual({
      type: 'EXTERNAL',
    });
  });

  it('passes paging through', () => {
    expect(buildParams({ bStart: 50, bSize: 25 })).toEqual({
      b_start: 50,
      b_size: 25,
    });
  });
});

describe('buildQueryString', () => {
  it('repeats status and keeps the other filters', () => {
    const query = buildQueryString({
      status: [404, -2],
      linkType: 'INTERNAL',
    });
    expect(query).toBe('status=404&status=-2&type=INTERNAL');
  });

  it('is empty when nothing is filtered, so the url stays clean', () => {
    expect(buildQueryString()).toBe('');
    expect(buildQueryString({ status: [], linkType: '' })).toBe('');
  });

  it('encodes values', () => {
    expect(buildQueryString({ linkType: 'A B' })).toBe('type=A+B');
  });
});

describe('pageToBStart', () => {
  it('turns a zero-based page into an offset', () => {
    expect(pageToBStart(0, 25)).toBe(0);
    expect(pageToBStart(2, 25)).toBe(50);
  });

  it('never goes negative', () => {
    expect(pageToBStart(-1, 25)).toBe(0);
  });
});

describe('totalPages', () => {
  it('rounds up', () => {
    expect(totalPages(26, 25)).toBe(2);
    expect(totalPages(50, 25)).toBe(2);
  });

  it('is at least one page, so paging never breaks on an empty report', () => {
    expect(totalPages(0, 25)).toBe(1);
    expect(totalPages(10, 0)).toBe(1);
  });
});

describe('formatLastUpdate', () => {
  it('returns null when no check has ever run', () => {
    // the caller must tell this apart from "the last check found nothing"
    expect(formatLastUpdate(null)).toBeNull();
    expect(formatLastUpdate(undefined)).toBeNull();
  });

  it('returns null on an unparseable date rather than "Invalid Date"', () => {
    expect(formatLastUpdate('not a date')).toBeNull();
  });

  it('formats in the given locale, not as an iso string', () => {
    const formatted = formatLastUpdate('2026-07-30T03:00:12', 'it-IT');
    expect(formatted).not.toBeNull();
    expect(formatted).not.toContain('T');
    expect(formatted).toContain('2026');
  });
});
