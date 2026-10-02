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

  it('marks an assessment as partial when only unavailable_services is set', async () => {
    const payload = assessmentPayload();
    payload.unavailable_services = ['adverse_media'];
    const assessment = await clientWith([jsonResponse(payload)]).kyc.assess('00445790');

    expect(assessment.unavailableServices).toEqual(['adverse_media']);
    expect(isPartial(assessment)).toBe(true);
  });

  it('parses psc_chain_depth_capped and unavailable_services, with defaults', async () => {
    const payload = assessmentPayload();
    payload.psc_chain_depth_capped = true;
    payload.unavailable_services = ['sanctions', 'gleif'];
    const capped = await clientWith([jsonResponse(payload)]).kyc.assess('00445790');
    expect(capped.pscChainDepthCapped).toBe(true);
    expect(capped.unavailableServices).toEqual(['sanctions', 'gleif']);

    const bare = assessmentPayload();
    delete bare.psc_chain_depth_capped;
    delete bare.unavailable_services;
    const defaults = await clientWith([jsonResponse(bare)]).kyc.assess('00445790');
    expect(defaults.pscChainDepthCapped).toBe(false);
    expect(defaults.unavailableServices).toEqual([]);
  });

  it('sends each new assess option', async () => {
    const fetch = mockFetch([jsonResponse(assessmentPayload())]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.kyc.assess('00445790', {
      dismissedMediaUrls: ['https://a.example', 'https://b.example'],
      dismissedLeakIds: ['n1', 'n2'],
      confirmedOfficerCompanyLinks: ['ACME HOLDINGS||01234567', 'FOO LTD||07654321'],
      confirmedFcaFrn: '123456',
      fcaNotApplicable: true,
    });

    const url = new URL(fetch.mock.calls[0]![0]);
    expect(url.searchParams.getAll('dismissed_media_url')).toEqual([
      'https://a.example',
      'https://b.example',
    ]);
    expect(url.searchParams.getAll('dismissed_leak_id')).toEqual(['n1', 'n2']);
    expect(url.searchParams.getAll('confirmed_officer_company_link')).toEqual([
      'ACME HOLDINGS||01234567',
      'FOO LTD||07654321',
    ]);
    expect(url.searchParams.getAll('confirmed_fca_frn')).toEqual(['123456']);
    expect(url.searchParams.getAll('fca_not_applicable')).toEqual(['true']);
  });

  it('omits fca_not_applicable and the other new options when unset or false', async () => {
    const fetch = mockFetch([jsonResponse(assessmentPayload()), jsonResponse(assessmentPayload())]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.kyc.assess('00445790');
    await client.kyc.assess('00445790', { fcaNotApplicable: false });

    for (const call of fetch.mock.calls) {
      const url = new URL(call[0]);
      for (const key of [
        'fca_not_applicable',
        'confirmed_fca_frn',
        'dismissed_media_url',
        'dismissed_leak_id',
        'confirmed_officer_company_link',
      ]) {
        expect(url.searchParams.has(key)).toBe(false);
      }
    }
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

  it('keeps raw on flags and rule results and drops non-object entries', async () => {
    const payload = assessmentPayload();
    payload.flags = [null, 'junk', ['x'], { code: 'X', extra: 1 }];
    payload.rule_results = [null, 42, { code: 'R', extra: 2 }];
    const assessment = await clientWith([jsonResponse(payload)]).kyc.assess('00445790');

    expect(assessment.flags).toHaveLength(1);
    expect(assessment.flags[0]!.code).toBe('X');
    expect(assessment.flags[0]!.raw.extra).toBe(1);
    expect(assessment.ruleResults).toHaveLength(1);
    expect(assessment.ruleResults[0]!.code).toBe('R');
    expect(assessment.ruleResults[0]!.raw.extra).toBe(2);
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
