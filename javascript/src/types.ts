/**
 * Shared types.
 *
 * Endpoints that proxy an upstream registry (Companies House, the FCA Register,
 * GLEIF, …) are typed as {@link JsonObject}: their shape is owned upstream, and
 * pinning it here would silently drop fields the moment upstream adds one. The
 * assessment result is the one response this API owns, so it is fully typed.
 */

/** Any JSON value. */
export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

/** A decoded JSON object, as returned by the registry-proxy endpoints. */
export type JsonObject = Record<string, any>;

/**
 * Severity of a risk flag, and the overall risk level of an assessment.
 *
 * `'unknown'` is a value this client version does not recognise. It ranks above
 * `'critical'` so it is never filtered out; the original string is on `raw`.
 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical' | 'unknown';

/** Outcome of a single rule within an assessment. */
export type RuleStatus = 'passed' | 'failed' | 'not_evaluated';

/** Ascending severity, for sorting and comparison. */
export const RISK_LEVEL_RANK: Record<RiskLevel, number> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
  unknown: 4,
};

/** A single risk signal raised against a company. */
export interface RiskFlag {
  code: string;
  severity: RiskLevel;
  description: string;
}

/** The per-rule breakdown of an assessment, including rules that passed. */
export interface RuleResult {
  code: string;
  name: string;
  description: string;
  severity: RiskLevel;
  status: RuleStatus;
  /** Why the rule failed, or why it could not be evaluated. */
  reason?: string | null;
}

/**
 * The result of running a rule set against one company.
 *
 * The `*Summary` fields hold the evidence each rule was evaluated against. Their
 * shapes mirror the corresponding standalone endpoints, so `officersSummary` and
 * `companies.officers()` describe the same data.
 */
export interface Assessment {
  // Identity and outcome
  companyNumber: string;
  companyName: string;
  riskLevel: RiskLevel;
  flags: RiskFlag[];
  /** When this assessment ran. */
  checkedAt: string;
  /** How fresh the oldest registry data point in this assessment is. */
  dataFetchedAt: string;

  // Companies House core data
  profile: JsonObject;
  officersSummary: JsonObject;
  pscSummary: JsonObject;
  pscChainDepth: number;
  pscStatementsSummary: JsonObject;
  chargesSummary: JsonObject;
  insolvencySummary: JsonObject;
  filingSummary: JsonObject;
  disqualificationsSummary: JsonObject;
  corporateDisqualificationsSummary: JsonObject;
  officerAppointmentsSummary: JsonObject;
  companyExemptionsSummary: JsonObject;
  confirmationStatementsSummary: JsonObject;
  cs01DocumentSummary: JsonObject;
  statementOfCapitalSummary: JsonObject;

  // Screening and external data
  sanctionsSummary: JsonObject;
  adverseMediaSummary: JsonObject;
  fcaSummary: JsonObject;
  individualInsolvencySummary: JsonObject;
  gleifSummary: JsonObject;
  offshoreLeaksSummary: JsonObject;
  vatSummary: JsonObject;

  // Run metadata
  /** Sources that did not answer in time. */
  timedOutServices: string[];
  /** Rules that raised an error rather than returning a verdict. */
  failedRules: string[];
  ruleResults: RuleResult[];
  /** Work deliberately deferred to a background job — poll again later. */
  pendingExtractions: string[];

  /** The untouched response body, so nothing this version doesn't model is lost. */
  raw: JsonObject;
}

/** The envelope returned when the API queues an assessment instead of running it inline. */
export interface QueuedJob {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  result?: JsonObject;
  error?: string;
}

const RISK_LEVELS = new Set<string>(['low', 'medium', 'high', 'critical']);
const RULE_STATUSES = new Set<string>(['passed', 'failed', 'not_evaluated']);

/**
 * Map an API severity string onto {@link RiskLevel}. Anything unrecognised (or
 * missing) becomes `'unknown'`, which ranks above `'critical'`, so a value this
 * version does not know can never make a result look lower-risk than it is.
 */
function toRiskLevel(value: unknown): RiskLevel {
  if (typeof value !== 'string') return 'unknown';
  const normalised = value.toLowerCase();
  return RISK_LEVELS.has(normalised) ? (normalised as RiskLevel) : 'unknown';
}

function toRuleStatus(value: unknown): RuleStatus {
  const normalised = String(value ?? '').toLowerCase();
  return RULE_STATUSES.has(normalised) ? (normalised as RuleStatus) : 'not_evaluated';
}

function asObject(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : {};
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

/** Convert a decoded `/v1/kyc/assess` body into a typed {@link Assessment}. */
export function parseAssessment(data: JsonObject): Assessment {
  const flags: RiskFlag[] = (Array.isArray(data.flags) ? data.flags : []).map(
    (flag: JsonObject): RiskFlag => ({
      code: String(flag?.code ?? ''),
      severity: toRiskLevel(flag?.severity),
      description: String(flag?.description ?? ''),
    }),
  );

  const ruleResults: RuleResult[] = (Array.isArray(data.rule_results) ? data.rule_results : []).map(
    (rule: JsonObject): RuleResult => ({
      code: String(rule?.code ?? ''),
      name: String(rule?.name ?? ''),
      description: String(rule?.description ?? ''),
      severity: toRiskLevel(rule?.severity),
      status: toRuleStatus(rule?.status),
      reason: rule?.reason ?? null,
    }),
  );

  return {
    companyNumber: String(data.company_number ?? ''),
    companyName: String(data.company_name ?? ''),
    riskLevel: toRiskLevel(data.risk_level),
    flags,
    checkedAt: String(data.checked_at ?? ''),
    dataFetchedAt: String(data.data_fetched_at ?? ''),

    profile: asObject(data.profile),
    officersSummary: asObject(data.officers_summary),
    pscSummary: asObject(data.psc_summary),
    pscChainDepth: Number(data.psc_chain_depth ?? 0),
    pscStatementsSummary: asObject(data.psc_statements_summary),
    chargesSummary: asObject(data.charges_summary),
    insolvencySummary: asObject(data.insolvency_summary),
    filingSummary: asObject(data.filing_summary),
    disqualificationsSummary: asObject(data.disqualifications_summary),
    corporateDisqualificationsSummary: asObject(data.corporate_disqualifications_summary),
    officerAppointmentsSummary: asObject(data.officer_appointments_summary),
    companyExemptionsSummary: asObject(data.company_exemptions_summary),
    confirmationStatementsSummary: asObject(data.confirmation_statements_summary),
    cs01DocumentSummary: asObject(data.cs01_document_summary),
    statementOfCapitalSummary: asObject(data.statement_of_capital_summary),

    sanctionsSummary: asObject(data.sanctions_summary),
    adverseMediaSummary: asObject(data.adverse_media_summary),
    fcaSummary: asObject(data.fca_summary),
    individualInsolvencySummary: asObject(data.individual_insolvency_summary),
    gleifSummary: asObject(data.gleif_summary),
    offshoreLeaksSummary: asObject(data.offshore_leaks_summary),
    vatSummary: asObject(data.vat_summary),

    timedOutServices: asStringArray(data.timed_out_services),
    failedRules: asStringArray(data.failed_rules),
    ruleResults,
    pendingExtractions: asStringArray(data.pending_extractions),

    raw: data,
  };
}

// ── Assessment helpers ───────────────────────────────────────────────────────
// Free functions rather than methods, so an Assessment stays a plain object that
// survives structuredClone, JSON round-trips and React state without surprises.

/** True when no rule in the set raised a flag. */
export function isClear(assessment: Assessment): boolean {
  return assessment.flags.length === 0;
}

/**
 * True when some data was unavailable, so the result is incomplete.
 *
 * A partial assessment is still usable, but an absent flag is not proof of a
 * clean result — treat it as "not yet screened".
 */
export function isPartial(assessment: Assessment): boolean {
  return (
    assessment.timedOutServices.length > 0 ||
    assessment.failedRules.length > 0 ||
    assessment.pendingExtractions.length > 0
  );
}

/**
 * Flags at `level` or more severe.
 *
 * A flag whose severity is `'unknown'` (a value this client version does not
 * recognise) ranks above `'critical'`, so it is never filtered out. The original
 * string is on `assessment.raw`.
 */
export function flagsAtOrAbove(assessment: Assessment, level: RiskLevel): RiskFlag[] {
  const threshold = RISK_LEVEL_RANK[level];
  return assessment.flags.filter((flag) => RISK_LEVEL_RANK[flag.severity] >= threshold);
}

/** Flags matching any of `levels`. */
export function flagsAt(assessment: Assessment, ...levels: RiskLevel[]): RiskFlag[] {
  const wanted = new Set(levels);
  return assessment.flags.filter((flag) => wanted.has(flag.severity));
}

/** True when a flag with `code` was raised, e.g. `"ACCOUNTS_OVERDUE"`. */
export function hasFlag(assessment: Assessment, code: string): boolean {
  return assessment.flags.some((flag) => flag.code === code);
}

/** The flag with `code`, or `undefined` when it was not raised. */
export function findFlag(assessment: Assessment, code: string): RiskFlag | undefined {
  return assessment.flags.find((flag) => flag.code === code);
}
