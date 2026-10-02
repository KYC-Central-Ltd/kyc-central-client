/** Assessment parsing, argument validation and queued-job polling. */

import { describe, expect, it } from 'vitest';

import {
  JobFailedError,
  JobTimeoutError,
  KYCCentral,
  findFlag,
  flagsAt,
  flagsAtOrAbove,
  hasFlag,
  isClear,
  isPartial,
  type Assessment,
} from '../src/index.js';
import { BASE_URL, assessmentPayload, jsonResponse, mockFetch } from './helpers.js';

function clientWith(responses: Response[]): KYCCentral {
  return new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch: mockFetch(responses) });
}

describe('assess', () => {
  it('parses the response into a typed assessment', async () => {
    const client = clientWith([jsonResponse(assessmentPayload())]);
    const assessment = await client.kyc.assess('00445790');

    expect(assessment.companyName).toBe('TESCO PLC');
    expect(assessment.riskLevel).toBe('medium');
    expect(assessment.pscChainDepth).toBe(2);
    expect(assessment.flags.map((f) => f.code)).toEqual([
      'ACCOUNTS_OVERDUE',
      'ADVERSE_MEDIA_UNCONFIRMED',
    ]);
    // Anything not mapped to a field is still reachable.
    expect(assessment.raw.profile.company_status).toBe('active');
  });

  it('exposes helpers over the flags', async () => {
    const client = clientWith([jsonResponse(assessmentPayload())]);
    const assessment = await client.kyc.assess('00445790');

    expect(isClear(assessment)).toBe(false);
    expect(isPartial(assessment)).toBe(false);
    expect(flagsAt(assessment, 'critical')).toEqual([]);
    expect(flagsAtOrAbove(assessment, 'high').map((f) => f.code)).toEqual(['ACCOUNTS_OVERDUE']);
    expect(flagsAtOrAbove(assessment, 'medium').map((f) => f.code)).toEqual(['ACCOUNTS_OVERDUE']);
    expect(hasFlag(assessment, 'ACCOUNTS_OVERDUE')).toBe(true);
    expect(hasFlag(assessment, 'NOT_RAISED')).toBe(false);
    expect(findFlag(assessment, 'NOT_RAISED')).toBeUndefined();
  });

  it('marks assessments affected by an upstream timeout as partial', async () => {
    const payload = assessmentPayload();
    payload.timed_out_services = ['sanctions'];
    const client = clientWith([jsonResponse(payload)]);

    expect(isPartial(await client.kyc.assess('00445790'))).toBe(true);
  });

  it('tolerates a severity this client version predates', async () => {
    const payload = assessmentPayload();
    payload.flags[0].severity = 'catastrophic';
    const client = clientWith([jsonResponse(payload)]);

    const assessment = await client.kyc.assess('00445790');
    expect(assessment.flags[0]!.severity).toBe('unknown');
    expect(assessment.raw.flags[0].severity).toBe('catastrophic');
  });

  it('maps an unrecognised severity or risk level to unknown, ranked above critical', async () => {
    const payload = assessmentPayload();
    payload.risk_level = 'severe';
    payload.flags[1].severity = 'severe';
    payload.flags[0].severity = 'HIGH';
    const assessment = await clientWith([jsonResponse(payload)]).kyc.assess('00445790');

    expect(assessment.riskLevel).toBe('unknown');
    expect(assessment.flags[1]!.severity).toBe('unknown');
    expect(assessment.flags[0]!.severity).toBe('high');
    expect(flagsAtOrAbove(assessment, 'high').map((f) => f.code)).toEqual([
      'ACCOUNTS_OVERDUE',
      'ADVERSE_MEDIA_UNCONFIRMED',
    ]);
    expect(flagsAtOrAbove(assessment, 'critical').map((f) => f.code)).toEqual([
      'ADVERSE_MEDIA_UNCONFIRMED',
    ]);
  });

  it('treats a missing severity as unknown', async () => {
    const payload = assessmentPayload();
    delete payload.flags[0].severity;
    const assessment = await clientWith([jsonResponse(payload)]).kyc.assess('00445790');
    expect(assessment.flags[0]!.severity).toBe('unknown');
  });

  it('requires exactly one of a company number and q', async () => {
    const client = clientWith([jsonResponse(assessmentPayload())]);

    await expect(client.kyc.assess({ q: '' } as never)).rejects.toThrow(/either/);
    await expect(client.kyc.assess('00445790', { q: 'tesco' })).rejects.toThrow(/not both/);
  });

  it('assesses the top search result when given a name', async () => {
    const fetch = mockFetch([jsonResponse(assessmentPayload())]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.kyc.assess({ q: 'tesco plc', ruleSetId: 'quick' });

    const url = new URL(fetch.mock.calls[0]![0]);
    expect(url.searchParams.get('q')).toBe('tesco plc');
    expect(url.searchParams.get('rule_set_id')).toBe('quick');
    expect(url.searchParams.has('company_number')).toBe(false);
  });
});

describe('queued assessments', () => {
  const queued = () => jsonResponse({ job_id: 'job-123', status: 'queued' }, 202);

  it('polls a queued job to completion', async () => {
    const fetch = mockFetch([
      queued(),
      jsonResponse({ job_id: 'job-123', status: 'running' }),
      jsonResponse({ job_id: 'job-123', status: 'done', result: assessmentPayload() }),
    ]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    const assessment = (await client.kyc.assess('00445790', {
      pollIntervalMs: 1,
    })) as Assessment;

    expect(assessment.companyName).toBe('TESCO PLC');
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls[1]![0]).toBe(`${BASE_URL}/v1/jobs/job-123`);
  });

  it('returns the raw envelope when wait is false', async () => {
    const client = clientWith([queued()]);
    const result = await client.kyc.assess('00445790', { wait: false });

    expect(result).toEqual({ job_id: 'job-123', status: 'queued' });
  });

  it('throws when the job fails', async () => {
    const client = clientWith([
      queued(),
      jsonResponse({ job_id: 'job-123', status: 'error', error: 'upstream exploded' }),
    ]);

    await expect(client.kyc.assess('00445790', { pollIntervalMs: 1 })).rejects.toThrow(
      JobFailedError,
    );
  });

  it('throws when the result has expired', async () => {
    const client = clientWith([queued(), jsonResponse({ job_id: 'job-123', status: 'done' })]);

    await expect(client.kyc.assess('00445790', { pollIntervalMs: 1 })).rejects.toThrow(
      /no longer available/,
    );
  });

  it('gives up after the poll timeout', async () => {
    const client = clientWith([queued(), jsonResponse({ job_id: 'job-123', status: 'running' })]);

    await expect(
      client.kyc.assess('00445790', { pollIntervalMs: 50, pollTimeoutMs: 1 }),
    ).rejects.toThrow(JobTimeoutError);
  });
});

describe('polling parameter validation', () => {
  it.each([
    ['pollIntervalMs', 0],
    ['pollIntervalMs', -1],
    ['pollTimeoutMs', 0],
    ['pollTimeoutMs', -1],
  ])('rejects %s = %d before any request', async (name, value) => {
    const fetch = mockFetch([jsonResponse(assessmentPayload())]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await expect(client.kyc.assess('00445790', { [name]: value })).rejects.toThrow(
      new TypeError(`${name} must be > 0`),
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
