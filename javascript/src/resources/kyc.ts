/**
 * The risk assessment endpoint — the reason this API exists.
 *
 * **Queued assessments.** A cold assessment fans out to a dozen upstream sources
 * and can take longer than a sensible HTTP timeout, so the API may accept the
 * request with `202 Accepted` and a job id instead of holding the connection
 * open. This client hides that: it polls the job to completion and resolves with
 * the finished {@link Assessment} either way. Pass `wait: false` to receive the
 * raw envelope and drive polling yourself.
 */

import { JobFailedError, JobTimeoutError } from '../errors.js';
import { seg, type Transport } from '../transport.js';
import { parseAssessment, type Assessment, type JsonObject, type QueuedJob } from '../types.js';
import type { CallOptions } from './companies.js';

export const DEFAULT_POLL_INTERVAL_MS = 2_000;
export const DEFAULT_POLL_TIMEOUT_MS = 180_000;

const QUEUED_STATUSES = new Set(['queued', 'running']);

export interface AssessOptions extends CallOptions {
  /** Company name to search — the top result is assessed. Alternative to a number. */
  q?: string;
  /** Rule set slug. Defaults to the API's `"default"` set. */
  ruleSetId?: string;
  /** Run one rule instead of a whole set, e.g. `"ACCOUNTS_OVERDUE"`. Overrides `ruleSetId`. */
  ruleCode?: string;
  /**
   * Adverse-media article URLs an analyst has already confirmed as genuine.
   *
   * Unconfirmed matches only ever raise a low-severity
   * `ADVERSE_MEDIA_UNCONFIRMED` flag; listing a URL here promotes that article
   * to its full severity.
   */
  confirmedMediaUrls?: string[];
  /** ICIJ Offshore Leaks match ids an analyst has confirmed, promoted the same way. */
  confirmedLeakIds?: string[];
  /** Confirmed PSC/shareholder identity links, each `"<psc name>||<shareholder name>"`. */
  confirmedPscShareholderLinks?: string[];
  /** Poll a queued assessment to completion. Default `true`. */
  wait?: boolean;
  /** Milliseconds between polls of a queued job. */
  pollIntervalMs?: number;
  /** Give up waiting after this many milliseconds. */
  pollTimeoutMs?: number;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** True when the API returned a job envelope rather than an assessment. */
function isQueued(payload: unknown): payload is QueuedJob {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    'job_id' in payload &&
    !('company_number' in payload)
  );
}

/**
 * Return the finished result, or `undefined` while the job is still running.
 *
 * @throws {JobFailedError} when the API reports the job as failed.
 */
function jobOutcome(state: QueuedJob): JsonObject | undefined {
  if (QUEUED_STATUSES.has(state.status)) return undefined;

  if (state.status === 'error') {
    throw new JobFailedError(state.error ?? 'The assessment job failed.', state.job_id);
  }
  if (state.status === 'done') {
    if (state.result && typeof state.result === 'object') return state.result;
    throw new JobFailedError(
      'The assessment finished but its result was no longer available — please re-run.',
      state.job_id,
    );
  }
  throw new JobFailedError(`Unexpected job status ${String(state.status)}.`, state.job_id);
}

/** Poll background jobs. You rarely need this — `kyc.assess()` polls for you. */
export class Jobs {
  constructor(private readonly transport: Transport) {}

  /**
   * Current state of a job.
   *
   * `status` is one of `queued`, `running`, `done` or `error`.
   */
  async get(jobId: string, options: CallOptions = {}): Promise<QueuedJob> {
    return this.transport.get(`/jobs/${seg(jobId, 'jobId')}`, options);
  }
}

/**
 * Run risk assessments. **Requires an API key** on every plan.
 *
 * Free-plan keys are capped at a fixed number of assessments per calendar month;
 * exceeding it throws {@link RateLimitError}. Cached results and failed runs do
 * not consume quota.
 */
export class Kyc {
  constructor(private readonly transport: Transport) {}

  /**
   * Assess one company against a rule set.
   *
   * Pass a company number, or `{ q }` to assess the top result for a name — but
   * prefer the number, so you always know which entity you screened.
   *
   * @throws {TypeError} Neither or both of `companyNumber` and `q` given, or a
   *   non-positive `pollIntervalMs` / `pollTimeoutMs`.
   * @throws {AuthenticationError} No API key configured.
   * @throws {NotFoundError} No such company, rule set or rule.
   * @throws {RateLimitError} Rate limit or monthly free quota hit.
   * @throws {JobTimeoutError} A queued assessment outran `pollTimeoutMs`.
   */
  async assess(companyNumber: string, options?: AssessOptions): Promise<Assessment>;
  async assess(options: AssessOptions & { q: string }): Promise<Assessment>;
  async assess(
    companyNumberOrOptions: string | (AssessOptions & { q: string }),
    maybeOptions: AssessOptions = {},
  ): Promise<Assessment | QueuedJob> {
    const isNumberForm = typeof companyNumberOrOptions === 'string';
    const options: AssessOptions = isNumberForm ? maybeOptions : companyNumberOrOptions;
    const companyNumber = isNumberForm ? companyNumberOrOptions : undefined;

    // Reject up front: a non-positive interval would poll the jobs endpoint in a hot loop.
    if (options.pollIntervalMs !== undefined && !(options.pollIntervalMs > 0)) {
      throw new TypeError('pollIntervalMs must be > 0');
    }
    if (options.pollTimeoutMs !== undefined && !(options.pollTimeoutMs > 0)) {
      throw new TypeError('pollTimeoutMs must be > 0');
    }

    if (!companyNumber && !options.q) {
      throw new TypeError('Provide either a company number or `q`.');
    }
    if (companyNumber && options.q) {
      throw new TypeError('Provide either a company number or `q`, not both.');
    }

    const payload = await this.transport.get<JsonObject | QueuedJob>('/kyc/assess', {
      params: {
        company_number: companyNumber,
        q: options.q,
        rule_set_id: options.ruleSetId,
        rule_code: options.ruleCode,
        confirmed_media_url: options.confirmedMediaUrls,
        confirmed_leak_id: options.confirmedLeakIds,
        confirmed_psc_shareholder_link: options.confirmedPscShareholderLinks,
      },
      signal: options.signal,
    });

    if (!isQueued(payload)) return parseAssessment(payload as JsonObject);
    if (options.wait === false) return payload;

    return parseAssessment(await this.awaitJob(payload.job_id, options));
  }

  private async awaitJob(jobId: string, options: AssessOptions): Promise<JsonObject> {
    const intervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
    const timeoutMs = options.pollTimeoutMs ?? DEFAULT_POLL_TIMEOUT_MS;
    const deadline = Date.now() + timeoutMs;

    for (;;) {
      const state = await this.transport.get<QueuedJob>(`/jobs/${seg(jobId, 'jobId')}`, {
        signal: options.signal,
      });

      const result = jobOutcome(state);
      if (result !== undefined) return result;

      if (Date.now() + intervalMs > deadline) {
        throw new JobTimeoutError(
          `Assessment job ${jobId} did not finish within ${timeoutMs}ms. It may still ` +
            'complete — re-running the same request will return the cached result once it does.',
          jobId,
        );
      }
      await sleep(intervalMs);
    }
  }
}

/** Discover the rule sets available to your key. */
export class RuleSets {
  constructor(private readonly transport: Transport) {}

  /** Every rule set you can run: built-ins plus your workspace sets. */
  async list(options: CallOptions = {}): Promise<JsonObject[]> {
    return this.transport.get('/rule-sets', options);
  }
}

/** Discover individual rules and the company fields they can test. */
export class Rules {
  constructor(private readonly transport: Transport) {}

  /** Every rule, with its code, severity and rationale. */
  async list(options: CallOptions = {}): Promise<JsonObject[]> {
    return this.transport.get('/rules', options);
  }

  /** Company data fields exposed to configurable rule conditions. */
  async fields(options: CallOptions = {}): Promise<unknown> {
    return this.transport.get('/rules/fields', options);
  }
}
