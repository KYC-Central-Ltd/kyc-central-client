/**
 * KYC Central — official JavaScript and TypeScript client for the UK company KYC
 * risk assessment API.
 *
 * ```ts
 * import { KYCCentral, flagsAtOrAbove } from '@kyccentral/sdk';
 *
 * const client = new KYCCentral();               // reads KYCCENTRAL_API_KEY
 * const assessment = await client.kyc.assess('00445790');
 *
 * for (const flag of flagsAtOrAbove(assessment, 'high')) {
 *   console.log(flag.code, flag.description);
 * }
 * ```
 *
 * @packageDocumentation
 * @see {@link https://kyccentral.co.uk/api-docs | API reference}
 */

export { KYCCentral } from './client.js';
export { KYCCentral as default } from './client.js';

export {
  API_PREFIX,
  DEFAULT_BASE_URL,
  DEFAULT_MAX_RETRIES,
  DEFAULT_TIMEOUT_MS,
  type ClientOptions,
  type FetchLike,
  type QueryParams,
} from './transport.js';

export {
  APIConnectionError,
  APIStatusError,
  APITimeoutError,
  AuthenticationError,
  BadRequestError,
  JobError,
  JobFailedError,
  JobTimeoutError,
  KYCCentralError,
  NotFoundError,
  PermissionDeniedError,
  RateLimitError,
  ServerError,
  ServiceUnavailableError,
  UnprocessableEntityError,
} from './errors.js';

export {
  RISK_LEVEL_RANK,
  findFlag,
  flagsAt,
  flagsAtOrAbove,
  hasFlag,
  isClear,
  isPartial,
  parseAssessment,
  type Assessment,
  type JsonObject,
  type JsonValue,
  type QueuedJob,
  type RiskFlag,
  type RiskLevel,
  type RuleResult,
  type RuleStatus,
} from './types.js';

export {
  DEFAULT_POLL_INTERVAL_MS,
  DEFAULT_POLL_TIMEOUT_MS,
  type AssessOptions,
} from './resources/kyc.js';

export {
  MAX_SCREEN_NAMES,
  type EntitiesOptions,
  type NodeOptions,
  type ScreenOptions,
  type SearchEntity,
} from './resources/screening.js';

export type {
  AdvancedSearchOptions,
  CallOptions,
  FilingHistoryOptions,
  PageOptions,
} from './resources/companies.js';

export type {
  AICallOptions,
  AdverseMediaOverviewOptions,
  AnalyseCompanyOptions,
  DocsAskOptions,
  DocsTurn,
  FilingExtractMode,
  FilingExtractOptions,
} from './resources/analysis.js';

export type { CharityOptions } from './resources/registries.js';

export { VERSION } from './version.js';
