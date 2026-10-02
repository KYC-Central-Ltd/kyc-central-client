/** Shared test helpers. Every test runs against a mocked fetch — no network. */

import { vi, type Mock } from 'vitest';

import type { JsonObject } from '../src/index.js';

export const BASE_URL = 'https://api.test.invalid';

/** Build a JSON `Response`, defaulting to 200. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/**
 * A `fetch` stub that returns each response in turn.
 *
 * Each call gets a fresh copy of the queued response, so a single `Response` can be
 * reused across retries. The copy is rebuilt from the body text rather than made with
 * `Response.clone()`: a cloned body is a tee, and cancelling one branch (as the
 * transport does when it retries) never settles while the other is unread. Once the
 * queue is exhausted the last response repeats, which keeps polling tests short.
 */
export function mockFetch(responses: Response[]): Mock {
  let index = 0;
  const bodies = new Map<Response, Promise<string>>();
  return vi.fn(async () => {
    const response = responses[Math.min(index, responses.length - 1)];
    index += 1;
    if (!response) throw new Error('mockFetch: no responses configured');
    // Non-standard stand-ins (e.g. an opaque redirect) are handed back via `clone()`.
    if (typeof response.text !== 'function') return response.clone();
    if (!bodies.has(response)) bodies.set(response, response.clone().text());
    const text = await bodies.get(response)!;
    return new Response(response.status === 204 ? null : text, {
      status: response.status,
      headers: response.headers,
    });
  });
}

/** A minimal but realistic `/v1/kyc/assess` body. */
export function assessmentPayload(): JsonObject {
  return {
    company_number: '00445790',
    company_name: 'TESCO PLC',
    risk_level: 'medium',
    checked_at: '2026-08-13T10:00:00+00:00',
    data_fetched_at: '2026-08-13T09:55:00+00:00',
    flags: [
      {
        code: 'ACCOUNTS_OVERDUE',
        severity: 'high',
        description: 'Annual accounts are 42 days overdue.',
      },
      {
        code: 'ADVERSE_MEDIA_UNCONFIRMED',
        severity: 'low',
        description: '3 possible adverse media matches require review.',
      },
    ],
    profile: { company_status: 'active' },
    officers_summary: { total: 12 },
    psc_summary: { total: 3 },
    psc_chain_depth: 2,
    rule_results: [
      {
        code: 'ACCOUNTS_OVERDUE',
        name: 'Accounts overdue',
        description: 'Checks whether annual accounts are past their due date.',
        severity: 'high',
        status: 'failed',
        reason: 'Annual accounts are 42 days overdue.',
      },
      {
        code: 'COMPANY_NOT_ACTIVE',
        name: 'Company not active',
        description: 'Checks the company is trading.',
        severity: 'critical',
        status: 'passed',
        reason: null,
      },
    ],
    timed_out_services: [],
    failed_rules: [],
    pending_extractions: [],
  };
}
