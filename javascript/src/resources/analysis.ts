/** AI analysis endpoints and the product documentation assistant. */

import { AI_TIMEOUT_MS, trimChargeKey, type Transport } from '../transport.js';
import type { JsonObject } from '../types.js';
import type { CallOptions } from './companies.js';

/** Options shared by the AI endpoints. */
export interface AICallOptions extends CallOptions {
  /**
   * Timeout for this call in milliseconds. Defaults to 120 000, or the client's
   * `timeoutMs` if that is longer.
   */
  timeoutMs?: number;
}

const FILING_EXTRACT_MODES = ['extract', 'verify'] as const;
export type FilingExtractMode = (typeof FILING_EXTRACT_MODES)[number];

export interface AnalyseCompanyOptions extends AICallOptions {
  /** Rule set whose findings should frame the analysis. */
  ruleSetId?: string;
  /** Override the AI provider, e.g. `"claude"`, `"gpt"`, `"gemini"`. */
  provider?: string;
  /** Restrict the write-up to named sections. At most 50. */
  sections?: string[];
  /** FCA Firm Reference Number, when the company is regulated and you know it. */
  fcaFrn?: string;
  /**
   * Evidence gathered elsewhere — confirmed screening hits, selected filings,
   * analyst-confirmed identity links — folded into the prompt so the analysis
   * reflects your review rather than raw unconfirmed matches.
   */
  context?: JsonObject;
}

export interface ChargeRegistrationOptions extends AICallOptions {
  /** Override the AI provider. */
  provider?: string;
}

export interface AdverseMediaOverviewOptions extends AICallOptions {
  provider?: string;
  /** Search results to summarise, as returned by `news.screenCompany()`. */
  results?: JsonObject;
}

export interface FilingExtractOptions extends AICallOptions {
  /** `"extract"` pulls structured data out; `"verify"` checks an existing extraction. */
  mode?: FilingExtractMode;
  provider?: string;
}

/** One prior turn of a documentation-assistant conversation. */
export interface DocsTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface DocsAskOptions extends AICallOptions {
  /** Prior turns for follow-up questions. At most 12. */
  history?: DocsTurn[];
}

/** `signal` plus the effective timeout: the per-call value, else max(client, 120 s). */
export function aiRequest(
  transport: Transport,
  options: AICallOptions,
): { signal?: AbortSignal; timeoutMs: number } {
  if (options.timeoutMs !== undefined && !(options.timeoutMs > 0)) {
    throw new TypeError('timeoutMs must be greater than 0');
  }
  return {
    signal: options.signal,
    timeoutMs: options.timeoutMs ?? Math.max(transport.timeoutMs, AI_TIMEOUT_MS),
  };
}

/**
 * LLM-written analyst commentary over an assessment.
 *
 * **Requires an active Professional subscription**, except for {@link status}.
 * These calls invoke a language model, so they are slower and dearer than the
 * deterministic rule engine — and, like any LLM output, the narrative is a
 * drafting aid for an analyst, not a compliance decision.
 */
export class Analysis {
  constructor(private readonly transport: Transport) {}

  /** Which AI providers are configured. Available without a subscription. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/analysis/status', options);
  }

  /** Write a narrative risk analysis for one company. */
  async company(companyNumber: string, options: AnalyseCompanyOptions = {}): Promise<JsonObject> {
    const body: JsonObject = { company_number: companyNumber };
    if (options.ruleSetId !== undefined) body.rule_set_id = options.ruleSetId;
    if (options.provider !== undefined) body.provider = options.provider;
    if (options.sections?.length) {
      if (options.sections.length > 50) {
        throw new TypeError(`sections accepts at most 50 entries, got ${options.sections.length}`);
      }
      body.sections = options.sections;
    }
    if (options.fcaFrn !== undefined) body.fca_frn = options.fcaFrn;
    if (options.context !== undefined) body.context = options.context;

    return this.transport.post('/analysis/company', {
      body,
      ...aiRequest(this.transport, options),
    });
  }

  /** Summarise adverse media results into a short overview. */
  async adverseMediaOverview(
    companyNumber: string,
    options: AdverseMediaOverviewOptions = {},
  ): Promise<JsonObject> {
    const body: JsonObject = { company_number: companyNumber };
    if (options.provider !== undefined) body.provider = options.provider;
    if (options.results !== undefined) body.results = options.results;

    return this.transport.post('/analysis/adverse-media-overview', {
      body,
      ...aiRequest(this.transport, options),
    });
  }

  /** Read a filing PDF with an LLM. */
  async filingExtract(
    companyNumber: string,
    transactionId: string,
    options: FilingExtractOptions = {},
  ): Promise<JsonObject> {
    const mode = options.mode ?? 'extract';
    if (!FILING_EXTRACT_MODES.includes(mode)) {
      throw new TypeError(
        `mode must be one of ${FILING_EXTRACT_MODES.join(', ')}, got '${String(mode)}'`,
      );
    }

    const body: JsonObject = {
      company_number: companyNumber,
      transaction_id: transactionId,
      mode,
    };
    if (options.provider !== undefined) body.provider = options.provider;

    return this.transport.post('/analysis/filing-extract', {
      body,
      ...aiRequest(this.transport, options),
    });
  }

  /**
   * Read a charge's "Registration of a charge" form with a vision-capable LLM, for
   * forms with no text layer (paper and pre-2013 filings) — the case
   * `companies.extractChargeRegistration` answers with `needs_ai`. Returns the same
   * merged record, with source `"ai_vision"`; an unreadable form returns
   * `{"available": false, "reason": ...}`. Spends AI credits on first use; a repeat
   * call for the same charge is served from the stored record.
   *
   * @throws {TypeError} `chargeKey` is blank.
   */
  async chargeRegistration(
    companyNumber: string,
    chargeKey: string,
    options: ChargeRegistrationOptions = {},
  ): Promise<JsonObject> {
    const body: JsonObject = {
      company_number: companyNumber,
      charge_key: trimChargeKey(chargeKey),
    };
    if (options.provider !== undefined) body.provider = options.provider;

    return this.transport.post('/analysis/charge-registration', {
      body,
      ...aiRequest(this.transport, options),
    });
  }
}

/** Ask questions about the product in natural language. */
export class Docs {
  constructor(private readonly transport: Transport) {}

  /** Ask the documentation assistant a question. Up to 2,000 characters. */
  async ask(message: string, options: DocsAskOptions = {}): Promise<JsonObject> {
    if (!message || !message.trim()) {
      throw new TypeError('message must be a non-empty string');
    }
    const body: JsonObject = { message };
    if (options.history?.length) {
      if (options.history.length > 12) {
        throw new TypeError(`history accepts at most 12 turns, got ${options.history.length}`);
      }
      body.history = options.history;
    }
    return this.transport.post('/docs/ask', { body, ...aiRequest(this.transport, options) });
  }
}
