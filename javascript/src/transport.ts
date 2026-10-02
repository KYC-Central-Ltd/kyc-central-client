/**
 * HTTP plumbing. Internal — the public surface is `client.ts`, `errors.ts` and
 * `types.ts`.
 *
 * Built on the platform `fetch`, so this package has no runtime dependencies and
 * runs unchanged on Node 22+, Deno, Bun, Cloudflare Workers and the browser.
 */

import {
  APIConnectionError,
  APIStatusError,
  APITimeoutError,
  statusErrorFromResponse,
} from './errors.js';
import { VERSION } from './version.js';

/** Production API. Override with `baseUrl` or `KYCCENTRAL_BASE_URL`. */
export const DEFAULT_BASE_URL = 'https://api.kyccentral.co.uk';

/** Every business endpoint is versioned. `/health` deliberately is not. */
export const API_PREFIX = '/v1';

export const DEFAULT_TIMEOUT_MS = 30_000;
/** Default timeout for the AI endpoints, which can run far longer than a lookup. */
export const AI_TIMEOUT_MS = 120_000;
export const DEFAULT_MAX_RETRIES = 2;

const RETRYABLE_STATUSES = new Set([408, 429, 500, 502, 503, 504]);
const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 8_000;
const MAX_BACKOFF_SECONDS = MAX_BACKOFF_MS / 1000;

export const API_KEY_ENV = 'KYCCENTRAL_API_KEY';
export const BASE_URL_ENV = 'KYCCENTRAL_BASE_URL';

/** A `fetch`-shaped function. Supply your own to add proxying, tracing or mocks. */
export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

/** Query parameter values. Arrays become repeated parameters. */
export type QueryParams = Record<
  string,
  string | number | boolean | Array<string | number> | null | undefined
>;

export interface RequestOptions {
  params?: QueryParams;
  body?: unknown;
  /** `/health` lives outside the `/v1` prefix. */
  versioned?: boolean;
  /** Abort this individual request. Combined with the client's own timeout. */
  signal?: AbortSignal;
  /** Replace the client's timeout for this one request, in milliseconds. */
  timeoutMs?: number;
}

export interface ClientOptions {
  /**
   * Your API key. Falls back to `KYCCENTRAL_API_KEY`. May be omitted: many
   * endpoints work anonymously at a lower rate limit.
   */
  apiKey?: string;
  /** API root. Falls back to `KYCCENTRAL_BASE_URL`, then to production. */
  baseUrl?: string;
  /** Per-request timeout in milliseconds. */
  timeoutMs?: number;
  /** Retries for timeouts, connection failures and retryable statuses. */
  maxRetries?: number;
  /** Extra headers on every request. */
  defaultHeaders?: Record<string, string>;
  /** Custom `fetch` implementation. */
  fetch?: FetchLike;
}

function readEnv(name: string): string | undefined {
  // Guarded so the bundle works in browsers and edge runtimes, where `process`
  // may not exist at all.
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
    ?.env;
  return env?.[name];
}

/** `node/20.1.0`, `deno/2.0.0` or `bun/1.1.0`, or undefined when the runtime is unknown. */
function runtimeLabel(): string | undefined {
  const g = globalThis as {
    process?: { versions?: { node?: string } };
    Deno?: { version?: { deno?: string } };
    Bun?: { version?: string };
  };
  // Check Deno and Bun first: both expose a Node-compatible `process.versions.node`.
  if (g.Deno?.version?.deno) return `deno/${g.Deno.version.deno}`;
  if (g.Bun?.version) return `bun/${g.Bun.version}`;
  if (g.process?.versions?.node) return `node/${g.process.versions.node}`;
  return undefined;
}

/**
 * `User-Agent` for server runtimes (Node, Deno, Bun).
 *
 * Skipped in browsers, which forbid or restrict setting it, and in any runtime that
 * can't be identified (browser web workers have no `window` either): there it is a
 * non-safelisted header that would add a CORS preflight requirement.
 */
function userAgent(): string | undefined {
  if (typeof (globalThis as { window?: unknown }).window !== 'undefined') return undefined;
  const runtime = runtimeLabel();
  return runtime ? `kyccentral-js/${VERSION} (${runtime})` : undefined;
}

/** Encode query parameters, dropping unset ones and repeating array values. */
export function buildQuery(params?: QueryParams): string {
  if (!params) return '';
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    // `null`/`undefined` mean "caller did not supply this" and must not be sent
    // as the literal strings "null" or "undefined".
    if (value === null || value === undefined) continue;

    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== null && item !== undefined) search.append(key, String(item));
      }
    } else {
      search.append(key, String(value));
    }
  }

  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

/**
 * Extract numeric Retry-After value from response headers, in seconds.
 * Returns undefined if absent or non-numeric.
 */
function retryAfterSeconds(response: Response): number | undefined {
  const raw = response.headers.get('Retry-After');
  if (raw) {
    const seconds = Number(raw);
    if (Number.isFinite(seconds)) {
      return seconds;
    }
  }
  return undefined;
}

/**
 * Milliseconds to wait before the next attempt.
 *
 * Honours `Retry-After` when present (up to the max backoff), otherwise backs off
 * exponentially with full jitter so a fleet recovering from one outage does not retry
 * in lockstep. Long `Retry-After` values (greater than the max backoff) are not waited
 * out; instead, the response is surfaced to the caller immediately so they can schedule
 * the retry themselves.
 */
function retryDelayMs(attempt: number, response?: Response): number {
  const seconds = response ? retryAfterSeconds(response) : undefined;
  if (seconds !== undefined) {
    return Math.max(0, Math.min(seconds * 1000, MAX_BACKOFF_MS));
  }
  const ceiling = Math.min(INITIAL_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
  return ceiling / 2 + Math.random() * (ceiling / 2);
}

const NEVER_CONNECTED_CODES = new Set(['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN']);

function errorCode(error: unknown): unknown {
  return (error as { code?: unknown } | null | undefined)?.code;
}

/** True when a fetch rejection proves the request never reached the server. */
function isConnectFailure(error: unknown): boolean {
  if (!(error instanceof TypeError)) return false;
  const cause = (error as { cause?: unknown }).cause;
  if (cause === null || cause === undefined) return false;
  if (NEVER_CONNECTED_CODES.has(errorCode(cause) as string)) return true;
  const errors = (cause as { errors?: unknown }).errors;
  return (
    Array.isArray(errors) &&
    errors.length > 0 &&
    errors.every((entry) => NEVER_CONNECTED_CODES.has(errorCode(entry) as string))
  );
}

/**
 * Whether a failed attempt may be sent again.
 *
 * GETs are idempotent, so any transient failure is retried. A POST may have been
 * processed (and billed) even when the client gave up, so it is retried only when
 * the connection was certainly never established, or when the server answered
 * 429/503 with `Retry-After` (explicitly "not processed, come back later").
 *
 * When a Retry-After header exceeds the max backoff (8 seconds), the response is
 * returned immediately so the caller can schedule the retry themselves.
 */
function isSafeToRetry(
  method: string,
  failure: { error: unknown } | { response: Response },
): boolean {
  if ('error' in failure) {
    return method === 'GET' || isConnectFailure(failure.error);
  }
  const { response } = failure;
  if (!RETRYABLE_STATUSES.has(response.status)) return false;

  // Long Retry-After values should not be waited out by retrying.
  const retryAfter = retryAfterSeconds(response);
  if (retryAfter !== undefined && retryAfter > MAX_BACKOFF_SECONDS) {
    return false;
  }

  if (method === 'GET') return true;
  return (
    (response.status === 429 || response.status === 503) && response.headers.has('Retry-After')
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Decode a response body, tolerating empty and non-JSON payloads. */
async function decode(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;

  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('json')) {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
  return text;
}

/** Combine the caller's abort signal with this request's timeout. */
function combineSignals(timeoutMs: number, external?: AbortSignal): AbortSignal {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (!external) return timeoutSignal;
  return AbortSignal.any([timeoutSignal, external]);
}

export class Transport {
  readonly apiKey?: string;
  readonly baseUrl: string;
  readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly defaultHeaders: Record<string, string>;
  private readonly fetchImpl: FetchLike;

  constructor(options: ClientOptions = {}) {
    // An empty or whitespace-only key (explicit, or from the environment) means "no key".
    const rawKey = options.apiKey ?? readEnv(API_KEY_ENV);
    this.apiKey = rawKey !== undefined && rawKey.trim() !== '' ? rawKey : undefined;
    this.baseUrl = (options.baseUrl ?? readEnv(BASE_URL_ENV) ?? DEFAULT_BASE_URL).replace(
      /\/+$/,
      '',
    );
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxRetries = options.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.defaultHeaders = options.defaultHeaders ?? {};

    if (this.timeoutMs <= 0) throw new Error('timeoutMs must be greater than 0');
    if (this.maxRetries < 0) throw new Error('maxRetries must be 0 or greater');

    const fetchImpl = options.fetch ?? globalThis.fetch;
    if (typeof fetchImpl !== 'function') {
      throw new Error(
        'No global fetch available. Use Node 22 or later, or pass a `fetch` implementation.',
      );
    }
    // Bound so that a global `fetch` keeps its expected `this`.
    this.fetchImpl = fetchImpl.bind(globalThis) as FetchLike;
  }

  get isAuthenticated(): boolean {
    return this.apiKey !== undefined;
  }

  private headers(hasBody: boolean): Record<string, string> {
    const callerSetAgent = Object.keys(this.defaultHeaders).some(
      (name) => name.toLowerCase() === 'user-agent',
    );
    const agent = callerSetAgent ? undefined : userAgent();
    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...(agent ? { 'User-Agent': agent } : {}),
      ...this.defaultHeaders,
    };
    if (hasBody) headers['Content-Type'] = 'application/json';
    if (this.apiKey) headers['X-API-Key'] = this.apiKey;
    return headers;
  }

  async request<T = unknown>(
    method: string,
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const { params, body, versioned = true, signal } = options;
    if (options.timeoutMs !== undefined && !(options.timeoutMs > 0)) {
      throw new TypeError('timeoutMs must be greater than 0');
    }
    const timeoutMs = options.timeoutMs ?? this.timeoutMs;
    const prefix = versioned ? API_PREFIX : '';
    const url = `${this.baseUrl}${prefix}${path.startsWith('/') ? path : `/${path}`}${buildQuery(params)}`;

    let lastError: unknown;

    for (let attempt = 0; attempt <= this.maxRetries; attempt += 1) {
      let response: Response;

      try {
        response = await this.fetchImpl(url, {
          method,
          headers: this.headers(body !== undefined),
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: combineSignals(timeoutMs, signal),
          // Never follow redirects: `X-API-Key` is a custom header that fetch would
          // forward to another origin. A 3xx surfaces as a status error instead.
          redirect: 'manual',
        });
      } catch (error) {
        // A caller-supplied signal firing is an intentional cancellation, not a
        // transient failure — surface it immediately rather than retrying.
        if (signal?.aborted) {
          throw new APITimeoutError(`${method} ${url} was aborted by the caller.`, error);
        }
        lastError = error;
        if (attempt >= this.maxRetries || !isSafeToRetry(method, { error })) {
          const isTimeout = error instanceof Error && error.name === 'TimeoutError';
          throw isTimeout
            ? new APITimeoutError(
                `${method} ${url} timed out after ${attempt + 1} attempt(s).`,
                error,
              )
            : new APIConnectionError(`${method} ${url} failed: ${String(error)}`, error);
        }
        await sleep(retryDelayMs(attempt));
        continue;
      }

      // Browsers resolve a manual redirect as an opaque, status-0 response with no
      // headers. Surface it explicitly; never retry it.
      if (response.type === 'opaqueredirect') {
        throw new APIStatusError(
          `${method} ${url} was redirected; redirects are not followed so the API key is never sent to another origin.`,
          { statusCode: response.status, headers: response.headers },
        );
      }

      if (
        attempt < this.maxRetries &&
        RETRYABLE_STATUSES.has(response.status) &&
        isSafeToRetry(method, { response })
      ) {
        // Release the connection; an unread body would otherwise pin it in the pool.
        await response.body?.cancel().catch(() => {});
        await sleep(retryDelayMs(attempt, response));
        continue;
      }

      // The body read can fail too (e.g. the timeout firing mid-stream). Never retry
      // once reading has started.
      let decoded: unknown;
      try {
        decoded = await decode(response);
      } catch (error) {
        const name = (error as { name?: unknown } | null | undefined)?.name;
        if (name === 'TimeoutError' || name === 'AbortError') {
          throw new APITimeoutError(
            signal?.aborted
              ? `${method} ${url} was aborted by the caller.`
              : `${method} ${url} timed out while reading the response body.`,
            error,
          );
        }
        throw new APIConnectionError(
          `${method} ${url} failed while reading the response body: ${String(error)}`,
          error,
        );
      }
      if (response.ok) return decoded as T;

      throw statusErrorFromResponse(response.status, decoded, response.headers, method, url);
    }

    /* c8 ignore next 2 -- unreachable: every loop exit above either returns or throws */
    throw new APIConnectionError(`${method} ${url} exhausted all retries.`, lastError);
  }

  get<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('GET', path, options);
  }

  post<T = unknown>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>('POST', path, options);
  }
}

/**
 * Validate and percent-encode a value interpolated into a URL path.
 *
 * Empty segments would silently collapse the path onto a different endpoint, and
 * officer ids are opaque upstream tokens, so both are checked and encoded.
 */
export function seg(value: string, name: string): string {
  if (value === null || value === undefined || String(value).trim() === '') {
    throw new TypeError(`${name} must be a non-empty string`);
  }
  return encodeURIComponent(String(value).trim());
}

/** Reject a blank charge key and return it trimmed. */
export function trimChargeKey(value: string): string {
  if (value === null || value === undefined || String(value).trim() === '') {
    throw new TypeError('chargeKey must be a non-empty string');
  }
  return String(value).trim();
}

/** Build the `{ names: [...] }` body used by the batch screening endpoints. */
export function namesBody(names: readonly string[], limit?: number): { names: string[] } {
  const cleaned = names.map((name) => String(name).trim()).filter(Boolean);
  if (cleaned.length === 0) {
    throw new TypeError('names must contain at least one non-empty string');
  }
  if (limit !== undefined && cleaned.length > limit) {
    throw new TypeError(`names accepts at most ${limit} entries, got ${cleaned.length}`);
  }
  return { names: cleaned };
}
