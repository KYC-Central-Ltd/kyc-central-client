/** Every resource method targets the URL and body the API documents. */

import { describe, expect, it, vi } from 'vitest';

import { KYCCentral, ServiceUnavailableError } from '../src/index.js';
import { BASE_URL, jsonResponse, mockFetch } from './helpers.js';

function client(): { client: KYCCentral; fetch: ReturnType<typeof mockFetch> } {
  const fetch = mockFetch([jsonResponse({})]);
  return { client: new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch }), fetch };
}

const CASES: Array<[string, (c: KYCCentral) => Promise<unknown>, string]> = [
  ['companies.get', (c) => c.companies.get('00445790'), '/v1/companies/00445790'],
  ['companies.dossier', (c) => c.companies.dossier('00445790'), '/v1/companies/00445790/dossier'],
  [
    'companies.officers',
    (c) => c.companies.officers('00445790'),
    '/v1/companies/00445790/officers',
  ],
  [
    'companies.pscs',
    (c) => c.companies.pscs('00445790'),
    '/v1/companies/00445790/persons-with-significant-control',
  ],
  [
    'companies.pscStatements',
    (c) => c.companies.pscStatements('00445790'),
    '/v1/companies/00445790/persons-with-significant-control-statements',
  ],
  [
    'companies.pscChainDepth',
    (c) => c.companies.pscChainDepth('00445790'),
    '/v1/companies/00445790/psc-chain-depth',
  ],
  [
    'companies.pscChainTree',
    (c) => c.companies.pscChainTree('00445790'),
    '/v1/companies/00445790/psc-chain-tree',
  ],
  [
    'companies.officerCompanyMatches',
    (c) => c.companies.officerCompanyMatches('00445790'),
    '/v1/companies/00445790/officer-company-matches',
  ],
  ['companies.charges', (c) => c.companies.charges('00445790'), '/v1/companies/00445790/charges'],
  [
    'companies.charge',
    (c) => c.companies.charge('00445790', 'chg1'),
    '/v1/companies/00445790/charges/chg1',
  ],
  [
    'companies.chargeRegistrations',
    (c) => c.companies.chargeRegistrations('00445790'),
    '/v1/companies/00445790/charges/registrations',
  ],
  [
    'companies.extractChargeRegistration',
    (c) => c.companies.extractChargeRegistration('00445790', 'k1'),
    '/v1/companies/00445790/charges/registration',
  ],
  [
    'analysis.chargeRegistration',
    (c) => c.analysis.chargeRegistration('00445790', 'k1'),
    '/v1/analysis/charge-registration',
  ],
  ['reports.data', (c) => c.reports.data('00445790'), '/v1/billing/report-data'],
  [
    'companies.insolvency',
    (c) => c.companies.insolvency('00445790'),
    '/v1/companies/00445790/insolvency',
  ],
  [
    'companies.disqualifications',
    (c) => c.companies.disqualifications('00445790'),
    '/v1/companies/00445790/disqualifications',
  ],
  [
    'companies.officerDisqualification',
    (c) => c.companies.officerDisqualification('00445790', 'off1'),
    '/v1/companies/00445790/officers/off1/disqualification',
  ],
  [
    'companies.filingHistory',
    (c) => c.companies.filingHistory('00445790'),
    '/v1/companies/00445790/filing-history',
  ],
  [
    'companies.filingExtract',
    (c) => c.companies.filingExtract('00445790', 'tx1'),
    '/v1/companies/00445790/filing-history/tx1/extract',
  ],
  [
    'companies.statementOfCapital',
    (c) => c.companies.statementOfCapital('00445790'),
    '/v1/companies/00445790/statement-of-capital',
  ],
  ['ruleSets.list', (c) => c.ruleSets.list(), '/v1/rule-sets'],
  ['rules.list', (c) => c.rules.list(), '/v1/rules'],
  ['rules.fields', (c) => c.rules.fields(), '/v1/rules/fields'],
  ['jobs.get', (c) => c.jobs.get('job-1'), '/v1/jobs/job-1'],
  ['jurisdictions.list', (c) => c.jurisdictions.list(), '/v1/jurisdictions'],
  ['jurisdictions.check', (c) => c.jurisdictions.check('Iran'), '/v1/jurisdictions/check'],
  [
    'offshoreJurisdictions.list',
    (c) => c.offshoreJurisdictions.list(),
    '/v1/offshore-jurisdictions',
  ],
  ['sanctions.status', (c) => c.sanctions.status(), '/v1/sanctions/status'],
  ['sanctions.meta', (c) => c.sanctions.meta(), '/v1/sanctions/meta'],
  ['sanctions.screen', (c) => c.sanctions.screen('Alice'), '/v1/sanctions/screen'],
  ['sanctions.entities', (c) => c.sanctions.entities(), '/v1/sanctions/entities'],
  ['news.status', (c) => c.news.status(), '/v1/news/status'],
  ['news.screenCompany', (c) => c.news.screenCompany('00445790'), '/v1/news/screen-company'],
  ['offshoreLeaks.status', (c) => c.offshoreLeaks.status(), '/v1/offshore-leaks/status'],
  ['offshoreLeaks.node', (c) => c.offshoreLeaks.node('n1'), '/v1/offshore-leaks/node/n1'],
  [
    'offshoreLeaks.screenCompany',
    (c) => c.offshoreLeaks.screenCompany('00445790'),
    '/v1/offshore-leaks/screen-company',
  ],
  ['gleif.company', (c) => c.gleif.company('00445790'), '/v1/gleif/company'],
  [
    'individualInsolvency.screenCompany',
    (c) => c.individualInsolvency.screenCompany('00445790'),
    '/v1/individual-insolvency/screen-company',
  ],
  ['charity.status', (c) => c.charity.status(), '/v1/charity/status'],
  ['charity.search', (c) => c.charity.search('oxfam'), '/v1/charity/search'],
  ['charity.get', (c) => c.charity.get('1234'), '/v1/charity/charity/1234'],
  ['charity.trustees', (c) => c.charity.trustees('1234'), '/v1/charity/charity/1234/trustees'],
  ['hmrcVat.status', (c) => c.hmrcVat.status(), '/v1/hmrc-vat/status'],
  ['hmrcVat.check', (c) => c.hmrcVat.check('GB123456789'), '/v1/hmrc-vat/check'],
  ['analysis.status', (c) => c.analysis.status(), '/v1/analysis/status'],
  ['dataSourceHealth', (c) => c.dataSourceHealth(), '/health/data-sources'],
];

describe('endpoint routing', () => {
  it.each(CASES)('%s hits %s', async (_name, call, path) => {
    const { client: c, fetch } = client();
    await call(c);
    expect(new URL(fetch.mock.calls[0]![0]).pathname).toBe(path);
  });
});

describe('request bodies', () => {
  it('posts a names body for batch sanctions screening', async () => {
    const { client: c, fetch } = client();
    await c.sanctions.screenNames(['Alice Example', '  Bob Example  ', '']);

    const body = JSON.parse(fetch.mock.calls[0]![1]!.body as string);
    // Blank entries dropped, surrounding whitespace trimmed.
    expect(body).toEqual({ names: ['Alice Example', 'Bob Example'] });
  });

  it('rejects empty name batches', async () => {
    const { client: c } = client();
    await expect(c.sanctions.screenNames([])).rejects.toThrow(/at least one/);
    await expect(c.offshoreLeaks.screenNames(['', '  '])).rejects.toThrow(/at least one/);
  });

  it('enforces the documented batch cap', async () => {
    const { client: c } = client();
    const names = Array.from({ length: 501 }, (_, i) => `name ${i}`);
    await expect(c.sanctions.screenNames(names)).rejects.toThrow(/at most 500/);
  });

  it('validates the entity search shape', async () => {
    const { client: c, fetch } = client();
    await c.news.searchEntities([{ key: 'psc-1', names: ['Alice Example', 'A. Example'] }]);

    const body = JSON.parse(fetch.mock.calls[0]![1]!.body as string);
    expect(body).toEqual({ entities: [{ key: 'psc-1', names: ['Alice Example', 'A. Example'] }] });

    await expect(c.news.searchEntities([{ key: '', names: ['Alice'] }])).rejects.toThrow(/'key'/);
    await expect(c.news.searchEntities([{ key: 'psc-1', names: [] }])).rejects.toThrow(
      /at least one name/,
    );
  });

  it('builds the analysis body', async () => {
    const { client: c, fetch } = client();
    await c.analysis.company('00445790', { ruleSetId: 'quick', sections: ['ownership'] });

    const body = JSON.parse(fetch.mock.calls[0]![1]!.body as string);
    expect(body).toEqual({
      company_number: '00445790',
      rule_set_id: 'quick',
      sections: ['ownership'],
    });
  });

  it('validates the filing extract mode', async () => {
    const { client: c } = client();
    await expect(
      c.analysis.filingExtract('00445790', 'tx1', { mode: 'summarise' as never }),
    ).rejects.toThrow(/mode must be one of/);
  });

  it('validates documentation questions', async () => {
    const { client: c } = client();
    await expect(c.docs.ask('   ')).rejects.toThrow(/non-empty/);
    await expect(
      c.docs.ask('hi', { history: Array(13).fill({ role: 'user', content: 'x' }) }),
    ).rejects.toThrow(/at most 12/);
  });

  it('sends a single-string advanced search filter once', async () => {
    const { client: c, fetch } = client();
    await c.companies.advancedSearch({
      companyNameIncludes: 'tesco',
      companyStatus: 'active',
      companyType: 'ltd',
      sicCodes: '47110',
    });

    const url = new URL(fetch.mock.calls[0]![0]);
    expect(url.searchParams.getAll('company_status')).toEqual(['active']);
    expect(url.searchParams.getAll('company_type')).toEqual(['ltd']);
    expect(url.searchParams.getAll('sic_codes')).toEqual(['47110']);
    expect(url.searchParams.get('company_name_includes')).toBe('tesco');
  });

  it('sends the charge key trimmed when extracting a registration', async () => {
    const { client: c, fetch } = client();
    await c.companies.extractChargeRegistration('00445790', '  094462310004 ');

    expect(fetch.mock.calls[0]![1]!.method).toBe('POST');
    expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
      charge_key: '094462310004',
    });
  });

  it('builds the charge registration analysis body', async () => {
    const { client: c, fetch } = client();
    await c.analysis.chargeRegistration('00445790', ' k1 ');
    await c.analysis.chargeRegistration('00445790', 'k1', { provider: 'claude' });

    expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
      company_number: '00445790',
      charge_key: 'k1',
    });
    expect(JSON.parse(fetch.mock.calls[1]![1]!.body as string)).toEqual({
      company_number: '00445790',
      charge_key: 'k1',
      provider: 'claude',
    });
  });

  it.each(['', '   '])('rejects blank charge key %j without a request', async (key) => {
    const { client: c, fetch } = client();
    await expect(c.companies.extractChargeRegistration('00445790', key)).rejects.toThrow(
      /chargeKey must be a non-empty string/,
    );
    await expect(c.analysis.chargeRegistration('00445790', key)).rejects.toThrow(
      /chargeKey must be a non-empty string/,
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('joins report sections and rule sets with commas', async () => {
    const { client: c, fetch } = client();
    await c.reports.data('00445790', {
      sections: ['assessment', 'sanctions'],
      ruleSetIds: ['quick', 'strict'],
      aiProvider: 'claude',
      fcaFrn: '123456',
      context: { accepted_gaps: ['sanctions'] },
    });

    expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
      company_number: '00445790',
      sections: 'assessment,sanctions',
      rule_set_ids: 'quick,strict',
      ai_provider: 'claude',
      fca_frn: '123456',
      context: { accepted_gaps: ['sanctions'] },
    });
  });

  it('passes report strings through and omits unset keys', async () => {
    const { client: c, fetch } = client();
    await c.reports.data('00445790', { sections: 'assessment,gleif', ruleSetIds: [] });
    await c.reports.data('00445790');

    expect(JSON.parse(fetch.mock.calls[0]![1]!.body as string)).toEqual({
      company_number: '00445790',
      sections: 'assessment,gleif',
    });
    expect(JSON.parse(fetch.mock.calls[1]![1]!.body as string)).toEqual({
      company_number: '00445790',
    });
  });

  it('does not retry a report that answers 503 with a long Retry-After', async () => {
    const limited = new Response('{"detail":"required check unavailable"}', {
      status: 503,
      headers: { 'content-type': 'application/json', 'Retry-After': '300' },
    });
    const fetch = mockFetch([limited, jsonResponse({})]);
    const c = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await expect(c.reports.data('00445790')).rejects.toSatisfy((error: unknown) => {
      expect(error).toBeInstanceOf(ServiceUnavailableError);
      expect((error as ServiceUnavailableError).retryAfter).toBe(300);
      return true;
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('AI endpoint timeouts', () => {
  const calls: Array<[string, (c: KYCCentral, opts?: { timeoutMs?: number }) => Promise<unknown>]> =
    [
      ['analysis.company', (c, o) => c.analysis.company('00445790', o)],
      ['analysis.adverseMediaOverview', (c, o) => c.analysis.adverseMediaOverview('00445790', o)],
      ['analysis.filingExtract', (c, o) => c.analysis.filingExtract('00445790', 'tx1', o)],
      ['analysis.chargeRegistration', (c, o) => c.analysis.chargeRegistration('00445790', 'k1', o)],
      ['reports.data', (c, o) => c.reports.data('00445790', o)],
      ['docs.ask', (c, o) => c.docs.ask('hello', o)],
    ];

  const timeoutsFor = async (
    run: (c: KYCCentral) => Promise<unknown>,
    clientTimeout?: number,
  ): Promise<number[]> => {
    const spy = vi.spyOn(AbortSignal, 'timeout');
    try {
      const fetch = mockFetch([jsonResponse({})]);
      const c = new KYCCentral({
        apiKey: 'k',
        baseUrl: BASE_URL,
        fetch,
        timeoutMs: clientTimeout,
      });
      await run(c);
      return spy.mock.calls.map((call) => call[0]);
    } finally {
      spy.mockRestore();
    }
  };

  it.each(calls)('%s defaults to 120 s', async (_name, call) => {
    expect(await timeoutsFor((c) => call(c))).toEqual([120_000]);
  });

  it.each(calls)('%s honours a per-call timeout', async (_name, call) => {
    expect(await timeoutsFor((c) => call(c, { timeoutMs: 5_000 }))).toEqual([5_000]);
  });

  it.each(calls)('%s keeps a larger client timeout', async (_name, call) => {
    expect(await timeoutsFor((c) => call(c), 300_000)).toEqual([300_000]);
  });

  it.each(calls)('%s rejects a non-positive timeout without a request', async (_name, call) => {
    const fetch = mockFetch([jsonResponse({})]);
    const c = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });
    await expect(call(c, { timeoutMs: 0 })).rejects.toThrow(TypeError);
    await expect(call(c, { timeoutMs: -1 })).rejects.toThrow(/greater than 0/);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('leaves other endpoints on the client timeout', async () => {
    expect(await timeoutsFor((c) => c.ruleSets.list())).toEqual([30_000]);
  });
});
