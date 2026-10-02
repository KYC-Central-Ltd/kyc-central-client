/**
 * Error types raised by the KYC Central client.
 *
 * Every error inherits from {@link KYCCentralError}, so one `catch` handles
 * transport failures and API errors alike. Narrower types let callers react
 * differently to, say, a rate limit than to a missing company.
 */

/** Base class for every error this library raises. */
export class KYCCentralError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
    // Restores the prototype chain when compiled down to ES5, so `instanceof`
    // keeps working for consumers on older targets.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** The request never produced a response (DNS, TLS, connection reset, offline). */
export class APIConnectionError extends KYCCentralError {
  /** The underlying transport failure, when there was one. Narrows `Error.cause`. */
  override readonly cause?: unknown;

  constructor(message = 'Could not reach the KYC Central API.', cause?: unknown) {
    super(message);
    this.cause = cause;
  }
}

/** The request timed out, or was aborted through a caller-supplied signal. */
export class APITimeoutError extends APIConnectionError {
  constructor(message = 'Request to the KYC Central API timed out.', cause?: unknown) {
    super(message, cause);
  }
}

/** Options accepted by {@link APIStatusError} and its subclasses. */
export interface APIStatusErrorOptions {
  statusCode: number;
  /** Message from the API's `{"detail": ...}` body, when it sent one. */
  detail?: string;
  /** The decoded response body. */
  body?: unknown;
  /** Response headers. Lookups through `.get()` are case-insensitive. */
  headers?: Headers;
}

/** The API returned a non-2xx status. */
export class APIStatusError extends KYCCentralError {
  readonly statusCode: number;
  readonly detail?: string;
  readonly body?: unknown;
  readonly headers: Headers;

  constructor(message: string, options: APIStatusErrorOptions) {
    super(message);
    this.statusCode = options.statusCode;
    this.detail = options.detail;
    this.body = options.body;
    this.headers = options.headers ?? new Headers();
  }
}

/** 400 — the request was malformed. */
export class BadRequestError extends APIStatusError {}

/**
 * 401 — no API key was sent, or the key is not valid.
 *
 * Most endpoints work anonymously at a reduced rate limit, but `kyc.assess()`
 * and the AI endpoints always require a key.
 */
export class AuthenticationError extends APIStatusError {}

/**
 * 403 — the key is valid but the plan does not include this endpoint.
 *
 * Almost always means an active Professional subscription is required, or that
 * an existing subscription is past due or cancelled. `detail` says which.
 */
export class PermissionDeniedError extends APIStatusError {}

/** 404 — no such company, officer, charge or filing. */
export class NotFoundError extends APIStatusError {}

/** 422 — the request failed the API's validation rules. `body` holds the details. */
export class UnprocessableEntityError extends APIStatusError {}

/** 429 — a rate limit or plan quota was exceeded. */
export class RateLimitError extends APIStatusError {
  /** Seconds to wait before retrying, from the `Retry-After` header. */
  readonly retryAfter?: number;

  constructor(message: string, options: APIStatusErrorOptions & { retryAfter?: number }) {
    super(message, options);
    this.retryAfter = options.retryAfter;
  }
}

/** 5xx — the API failed to handle an otherwise valid request. */
export class ServerError extends APIStatusError {}

/** 503 — a dependency the API needs is temporarily unavailable. */
export class ServiceUnavailableError extends ServerError {
  /** Seconds to wait before retrying, from the `Retry-After` header. */
  readonly retryAfter?: number;

  constructor(message: string, options: APIStatusErrorOptions & { retryAfter?: number }) {
    super(message, options);
    this.retryAfter = options.retryAfter;
  }
}

/**
 * A queued assessment did not produce a result.
 *
 * The API queues expensive assessments rather than holding the connection open;
 * this client polls them to completion for you. These errors surface when that
 * polling cannot deliver a result.
 */
export class JobError extends KYCCentralError {
  readonly jobId?: string;

  constructor(message: string, jobId?: string) {
    super(message);
    this.jobId = jobId;
  }
}

/** The API reported the queued assessment as failed. */
export class JobFailedError extends JobError {}

/**
 * The queued assessment did not finish within `pollTimeoutMs`.
 *
 * It may still complete server-side; re-issuing the same request will usually
 * return the cached result once it does.
 */
export class JobTimeoutError extends JobError {}

/**
 * Flatten an API error body into one human-readable sentence.
 *
 * The API returns `{"detail": "..."}` for handled errors, and FastAPI's
 * `{"detail": [{loc, msg}, ...]}` list form for validation failures.
 */
function extractDetail(body: unknown, fallback: string): string {
  if (typeof body !== 'object' || body === null) return fallback;

  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (typeof item !== 'object' || item === null) return String(item);
        const entry = item as { loc?: unknown[]; msg?: unknown };
        const loc = Array.isArray(entry.loc)
          ? entry.loc.filter((part) => part !== 'body').join('.')
          : '';
        const msg = entry.msg ?? 'invalid value';
        return loc ? `${loc}: ${String(msg)}` : String(msg);
      })
      .join('; ');
  }

  return fallback;
}

const STATUS_MAP: Record<
  number,
  new (message: string, options: APIStatusErrorOptions) => APIStatusError
> = {
  400: BadRequestError,
  401: AuthenticationError,
  403: PermissionDeniedError,
  404: NotFoundError,
  422: UnprocessableEntityError,
};

/** Seconds from a numeric `Retry-After` header, else `undefined`. */
function parseRetryAfter(headers: Headers): number | undefined {
  const raw = headers.get('Retry-After');
  const parsed = raw === null ? Number.NaN : Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/** Build the most specific error class for a failed response. */
export function statusErrorFromResponse(
  statusCode: number,
  body: unknown,
  headers: Headers,
  method: string,
  url: string,
): APIStatusError {
  const detail = extractDetail(body, `HTTP ${statusCode}`);
  const message = `${method} ${url} failed with ${statusCode}: ${detail}`;
  const options: APIStatusErrorOptions = { statusCode, detail, body, headers };

  if (statusCode === 429) {
    return new RateLimitError(message, { ...options, retryAfter: parseRetryAfter(headers) });
  }
  if (statusCode === 503) {
    return new ServiceUnavailableError(message, {
      ...options,
      retryAfter: parseRetryAfter(headers),
    });
  }

  const ErrorClass = STATUS_MAP[statusCode] ?? (statusCode >= 500 ? ServerError : APIStatusError);
  return new ErrorClass(message, options);
}
