/** Client construction, headers, URL building and retry behaviour. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  APIConnectionError,
  APIStatusError,
  APITimeoutError,
  DEFAULT_BASE_URL,
  KYCCentral,
  NotFoundError,
} from '../src/index.js';
import { BASE_URL, jsonResponse, mockFetch } from './helpers.js';

describe('construction', () => {
  const originalKey = process.env.KYCCENTRAL_API_KEY;
  const originalBase = process.env.KYCCENTRAL_BASE_URL;

  beforeEach(() => {
    delete process.env.KYCCENTRAL_API_KEY;
    delete process.env.KYCCENTRAL_BASE_URL;
  });

  afterEach(() => {
    if (originalKey === undefined) delete process.env.KYCCENTRAL_API_KEY;
    else process.env.KYCCENTRAL_API_KEY = originalKey;
    if (originalBase === undefined) delete process.env.KYCCENTRAL_BASE_URL;
    else process.env.KYCCENTRAL_BASE_URL = originalBase;
  });

  it('defaults to the production base URL and anonymous access', () => {
    const client = new KYCCentral();
    expect(client.baseUrl).toBe(DEFAULT_BASE_URL);
    expect(client.isAuthenticated).toBe(false);
  });

  it('reads credentials from the environment', () => {
    process.env.KYCCENTRAL_API_KEY = 'env-key';
    process.env.KYCCENTRAL_BASE_URL = 'https://dev-api.test.invalid/';
    const client = new KYCCentral();
    expect(client.isAuthenticated).toBe(true);
    // Trailing slash is normalised away so path joins never double up.
    expect(client.baseUrl).toBe('https://dev-api.test.invalid');
  });

  it('prefers explicit options over the environment', () => {
    process.env.KYCCENTRAL_API_KEY = 'env-key';
    const client = new KYCCentral({ apiKey: 'explicit', baseUrl: BASE_URL });
    expect(client.baseUrl).toBe(BASE_URL);
  });

  it.each([
    ['an explicit empty key', { apiKey: '' }, undefined],
    ['an explicit whitespace key', { apiKey: '   ' }, undefined],
    ['an empty env var', {}, ''],
    ['a whitespace env var', {}, '  '],
    ['an explicit empty key over a set env var', { apiKey: '' }, 'env-key'],
  ])('treats %s as no key', async (_label, options, env) => {
    if (env !== undefined) process.env.KYCCENTRAL_API_KEY = env;
    const fetch = mockFetch([jsonResponse({})]);
    const client = new KYCCentral({ baseUrl: BASE_URL, fetch, ...options });
    expect(client.isAuthenticated).toBe(false);

    await client.health();
    const init = fetch.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).has('X-API-Key')).toBe(false);
  });

  it.each([
    ['timeoutMs', { timeoutMs: 0 }],
    ['negative timeoutMs', { timeoutMs: -1 }],
    ['maxRetries', { maxRetries: -1 }],
  ])('rejects invalid %s', (_label, options) => {
    expect(() => new KYCCentral(options)).toThrow();
  });
});

describe('requests', () => {
  it('sends the API key and an Accept header', async () => {
    const fetch = mockFetch([jsonResponse([])]);
    const client = new KYCCentral({ apiKey: 'test-key', baseUrl: BASE_URL, fetch });

    await client.ruleSets.list();

    const [, init] = fetch.mock.calls[0]!;
    const headers = init!.headers as Record<string, string>;
    expect(headers['X-API-Key']).toBe('test-key');
    expect(headers['Accept']).toBe('application/json');
  });

  it('omits the API key header when anonymous', async () => {
    const fetch = mockFetch([jsonResponse({})]);
    const client = new KYCCentral({ baseUrl: BASE_URL, fetch });

    await client.jurisdictions.list();

    const headers = fetch.mock.calls[0]![1]!.headers as Record<string, string>;
    expect(headers['X-API-Key']).toBeUndefined();
  });

  it('sets Content-Type only when there is a body', async () => {
    const fetch = mockFetch([jsonResponse({}), jsonResponse({})]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.sanctions.status();
    expect(
      (fetch.mock.calls[0]![1]!.headers as Record<string, string>)['Content-Type'],
    ).toBeUndefined();

    await client.sanctions.screenNames(['Alice Example']);
    expect((fetch.mock.calls[1]![1]!.headers as Record<string, string>)['Content-Type']).toBe(
      'application/json',
    );
  });

  it('versions business endpoints but not /health', async () => {
    const fetch = mockFetch([jsonResponse({ status: 'ok' }), jsonResponse([])]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.health();
    expect(fetch.mock.calls[0]![0]).toBe(`${BASE_URL}/health`);

    await client.ruleSets.list();
    expect(fetch.mock.calls[1]![0]).toBe(`${BASE_URL}/v1/rule-sets`);
  });

  it('drops unset query parameters', async () => {
    const fetch = mockFetch([jsonResponse({ items: [] })]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.companies.search('tesco');

    const url = new URL(fetch.mock.calls[0]![0]);
    expect(url.searchParams.get('q')).toBe('tesco');
    expect(url.searchParams.has('items_per_page')).toBe(false);
    expect(url.searchParams.has('start_index')).toBe(false);
  });

  it('repeats array parameters once per value', async () => {
    const fetch = mockFetch([jsonResponse({ company_number: '00445790', flags: [] })]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    await client.kyc.assess('00445790', {
      confirmedMediaUrls: ['https://a.example', 'https://b.example'],
    });

    const url = new URL(fetch.mock.calls[0]![0]);
    expect(url.searchParams.getAll('confirmed_media_url')).toEqual([
      'https://a.example',
      'https://b.example',
    ]);
  });

  it('percent-encodes path segments', async () => {
    const fetch = mockFetch([jsonResponse({})]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch });

    // Officer ids are opaque upstream tokens and can contain URL-significant bytes.
    await client.companies.officerAppointments('abc/def+gh');

    expect(fetch.mock.calls[0]![0]).toContain('abc%2Fdef%2Bgh');
  });

  it.each(['', '   '])('rejects blank path segments (%j)', async (blank) => {
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch: mockFetch([]) });
    await expect(client.companies.get(blank)).rejects.toThrow(/companyNumber/);
  });

  it('sends custom default headers', async () => {
    const fetch = mockFetch([jsonResponse([])]);
    const client = new KYCCentral({
      apiKey: 'k',
      baseUrl: BASE_URL,
      fetch,
      defaultHeaders: { 'X-Trace': 'abc' },
    });

    await client.ruleSets.list();

    expect((fetch.mock.calls[0]![1]!.headers as Record<string, string>)['X-Trace']).toBe('abc');
  });
});

describe('retries', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('retries retryable statuses then succeeds', async () => {
    const fetch = mockFetch([
      jsonResponse({ detail: 'warming up' }, 503),
      jsonResponse([{ id: 'default' }]),
    ]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).resolves.toEqual([{ id: 'default' }]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry client errors', async () => {
    const fetch = mockFetch([jsonResponse({ detail: 'Company not found' }, 404)]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 3 });

    await expect(client.companies.get('99999999')).rejects.toBeInstanceOf(NotFoundError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('surfaces connection errors after exhausting retries', async () => {
    const fetch = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 1 });

    await expect(client.ruleSets.list()).rejects.toBeInstanceOf(APIConnectionError);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('reports timeouts distinctly from other connection failures', async () => {
    const timeout = new Error('The operation was aborted due to timeout');
    timeout.name = 'TimeoutError';
    const fetch = vi.fn().mockRejectedValue(timeout);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 0 });

    await expect(client.ruleSets.list()).rejects.toBeInstanceOf(APITimeoutError);
  });

  it('does not retry a caller-initiated abort', async () => {
    const controller = new AbortController();
    const fetch = vi.fn().mockImplementation(() => {
      controller.abort();
      const error = new Error('aborted');
      error.name = 'AbortError';
      return Promise.reject(error);
    });
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 3 });

    await expect(client.ruleSets.list({ signal: controller.signal })).rejects.toBeInstanceOf(
      APITimeoutError,
    );
    // An intentional cancellation must not be retried into three more requests.
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('POST retry policy', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const ok = () => jsonResponse({ ok: true });
  const post = (client: KYCCentral) => client.docs.ask('hello');
  const make = (fetch: ReturnType<typeof vi.fn>) =>
    new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });
  const fetchError = (code: string, message = 'boom') =>
    new TypeError('fetch failed', { cause: Object.assign(new Error(message), { code }) });
  const timeoutError = () => {
    const error = new Error('The operation was aborted due to timeout');
    error.name = 'TimeoutError';
    return error;
  };

  it('does not retry a POST that timed out', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(timeoutError()).mockResolvedValue(ok());
    await expect(post(make(fetch))).rejects.toBeInstanceOf(APITimeoutError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries a POST when the connection was refused', async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError('ECONNREFUSED', 'connect ECONNREFUSED'))
      .mockResolvedValue(ok());
    await expect(post(make(fetch))).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('retries a POST when every happy-eyeballs address failed to connect', async () => {
    const cause = Object.assign(new AggregateError([]), {
      errors: [{ code: 'ECONNREFUSED' }, { code: 'ENOTFOUND' }],
    });
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('fetch failed', { cause }))
      .mockResolvedValue(ok());
    await expect(post(make(fetch))).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry a POST when only some happy-eyeballs addresses were refused', async () => {
    const cause = Object.assign(new AggregateError([]), {
      errors: [{ code: 'ECONNREFUSED' }, { code: 'ETIMEDOUT' }],
    });
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('fetch failed', { cause }))
      .mockResolvedValue(ok());
    await expect(post(make(fetch))).rejects.toBeInstanceOf(APIConnectionError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('does not retry a POST that gets a 502', async () => {
    const fetch = mockFetch([jsonResponse({ detail: 'bad gateway' }, 502), ok()]);
    await expect(post(make(fetch))).rejects.toMatchObject({ statusCode: 502 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries a POST on 503 with Retry-After', async () => {
    const limited = new Response('{}', {
      status: 503,
      headers: { 'content-type': 'application/json', 'Retry-After': '0' },
    });
    const fetch = mockFetch([limited, ok()]);
    await expect(post(make(fetch))).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry a POST on 503 without Retry-After', async () => {
    const fetch = mockFetch([jsonResponse({ detail: 'down' }, 503), ok()]);
    await expect(post(make(fetch))).rejects.toMatchObject({ statusCode: 503 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('does not retry a POST on an unsafe transport error', async () => {
    const fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError('UND_ERR_SOCKET', 'other side closed'))
      .mockResolvedValue(ok());
    await expect(post(make(fetch))).rejects.toBeInstanceOf(APIConnectionError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('still retries a GET that times out', async () => {
    const fetch = vi.fn().mockRejectedValueOnce(timeoutError()).mockResolvedValue(jsonResponse([]));
    await expect(make(fetch).ruleSets.list()).resolves.toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe('long Retry-After values', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not retry a GET on 429 with Retry-After > 8 seconds', async () => {
    const limited = new Response('{"detail": "Too many requests"}', {
      status: 429,
      headers: { 'content-type': 'application/json', 'Retry-After': '60' },
    });
    const fetch = mockFetch([limited, jsonResponse([])]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).rejects.toMatchObject({
      statusCode: 429,
      retryAfter: 60,
    });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('retries a GET on 429 with Retry-After <= 8 seconds', async () => {
    const limited = new Response('{"detail": "Too many requests"}', {
      status: 429,
      headers: { 'content-type': 'application/json', 'Retry-After': '0' },
    });
    const fetch = mockFetch([limited, jsonResponse([])]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).resolves.toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('does not retry a GET on 503 with Retry-After > 8 seconds', async () => {
    const limited = new Response('{"detail": "Service Unavailable"}', {
      status: 503,
      headers: { 'content-type': 'application/json', 'Retry-After': '60' },
    });
    const fetch = mockFetch([limited, jsonResponse([])]);
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).rejects.toMatchObject({ statusCode: 503 });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('redirects', () => {
  it('does not follow a 3xx and surfaces it as a status error', async () => {
    const fetch = mockFetch([
      new Response(null, { status: 302, headers: { location: 'https://evil.example/' } }),
    ]);
    const client = new KYCCentral({ apiKey: 'test-key', baseUrl: BASE_URL, fetch });

    const error = await client.health().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(APIStatusError);
    expect((error as APIStatusError).statusCode).toBe(302);
    expect((error as APIStatusError).headers.get('location')).toBe('https://evil.example/');
    expect(fetch).toHaveBeenCalledTimes(1);
    const init = fetch.mock.calls[0]?.[1] as RequestInit;
    expect(init.redirect).toBe('manual');
  });

  it('raises on a browser opaque redirect without retrying', async () => {
    const opaque = {
      type: 'opaqueredirect',
      status: 0,
      ok: false,
      headers: new Headers(),
      clone() {
        return this;
      },
    } as unknown as Response;
    const fetch = mockFetch([opaque]);
    const client = new KYCCentral({ apiKey: 'test-key', baseUrl: BASE_URL, fetch });

    const error = await client.health().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(APIStatusError);
    expect((error as APIStatusError).statusCode).toBe(0);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('response body handling', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function fakeResponse(status: number, text: () => Promise<string>, cancel = vi.fn()): Response {
    return {
      status,
      ok: status >= 200 && status < 300,
      type: 'basic',
      headers: new Headers({ 'content-type': 'application/json' }),
      body: { cancel },
      text,
    } as unknown as Response;
  }

  it('releases the body of a response that is retried', async () => {
    const cancel = vi.fn(() => Promise.resolve());
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(fakeResponse(503, () => Promise.resolve(''), cancel))
      .mockResolvedValueOnce(jsonResponse([{ id: 'default' }]));
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).resolves.toEqual([{ id: 'default' }]);
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('raises APITimeoutError when reading the body times out, without retrying', async () => {
    const timeout = new Error('The operation was aborted due to timeout');
    timeout.name = 'TimeoutError';
    const fetch = vi.fn().mockResolvedValue(fakeResponse(200, () => Promise.reject(timeout)));
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).rejects.toBeInstanceOf(APITimeoutError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('raises APIConnectionError when reading the body fails otherwise', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(fakeResponse(200, () => Promise.reject(new Error('socket hang up'))));
    const client = new KYCCentral({ apiKey: 'k', baseUrl: BASE_URL, fetch, maxRetries: 2 });

    await expect(client.ruleSets.list()).rejects.toBeInstanceOf(APIConnectionError);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
