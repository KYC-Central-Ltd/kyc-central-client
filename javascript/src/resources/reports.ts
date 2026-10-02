/** Full report data as JSON. */

import type { Transport } from '../transport.js';
import type { JsonObject } from '../types.js';
import { aiRequest, type AICallOptions } from './analysis.js';

export interface ReportDataOptions extends AICallOptions {
  /**
   * Any of `assessment`, `company_data`, `filings`, `disqualifications`, `fca`,
   * `gleif`, `individual_insolvency`, `confirmation_statements`, `sanctions`,
   * `adverse_media`, `ai_analysis`, `offshore_leaks`. Defaults to `assessment`,
   * `company_data`, `sanctions`. Leave out `ai_analysis` for a report with no
   * AI-written content. An array is sent comma-joined.
   */
  sections?: string | string[];
  /** Rule sets to run; their rules are combined and deduplicated. An array is sent comma-joined. */
  ruleSetIds?: string | string[];
  /** Override the AI provider. */
  aiProvider?: string;
  /** A confirmed FCA firm reference number. Once given, the FCA lookup becomes a required check. */
  fcaFrn?: string;
  /**
   * The analyst's confirmations. Its `accepted_gaps` (with `accepted_gaps_at`, no
   * more than 24 hours old) lists `sanctions` / `adverse_media` / `offshore_leaks`
   * checks to proceed without if they are unavailable; those come back under
   * `generated_without`.
   */
  context?: JsonObject;
}

/** A list becomes one comma-joined string; a plain string passes through; empty is unset. */
function commaJoined(value: string | string[] | undefined): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value === 'string') return value;
  return value.length > 0 ? value.join(',') : undefined;
}

/** The full report as JSON rather than a PDF. **Requires an API key.** */
export class Reports {
  constructor(private readonly transport: Transport) {}

  /**
   * The full report as JSON instead of a PDF: the assessment, flags per rule set and
   * every section's data. Requires an API key and uses one PDF report credit (a
   * subscriber's monthly allowance first, then purchased credits).
   *
   * A report is never returned with a required check missing: that is a 503 with
   * `Retry-After` (about five minutes) and the credit is returned. The client does
   * not retry it; wait for the error's `retryAfter` and call again.
   *
   * @throws {ServiceUnavailableError} A required check was unavailable.
   */
  async data(companyNumber: string, options: ReportDataOptions = {}): Promise<JsonObject> {
    const body: JsonObject = { company_number: companyNumber };
    const sections = commaJoined(options.sections);
    if (sections !== undefined) body.sections = sections;
    const ruleSetIds = commaJoined(options.ruleSetIds);
    if (ruleSetIds !== undefined) body.rule_set_ids = ruleSetIds;
    if (options.aiProvider !== undefined) body.ai_provider = options.aiProvider;
    if (options.fcaFrn !== undefined) body.fca_frn = options.fcaFrn;
    if (options.context !== undefined) body.context = options.context;

    return this.transport.post('/billing/report-data', {
      body,
      ...aiRequest(this.transport, options),
    });
  }
}
