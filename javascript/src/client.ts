/** The client entry point. */

import { Transport, type ClientOptions } from './transport.js';
import { Analysis, Docs } from './resources/analysis.js';
import { Companies, type CallOptions } from './resources/companies.js';
import { Jobs, Kyc, Rules, RuleSets } from './resources/kyc.js';
import { Charity, HmrcVat, Jurisdictions, OffshoreJurisdictions } from './resources/registries.js';
import { Reports } from './resources/reports.js';
import {
  Gleif,
  IndividualInsolvency,
  News,
  OffshoreLeaks,
  Sanctions,
} from './resources/screening.js';
import type { JsonObject } from './types.js';

/**
 * Client for the KYC Central API.
 *
 * @example
 * ```ts
 * import { KYCCentral } from '@kyccentral/sdk';
 *
 * const client = new KYCCentral();            // reads KYCCENTRAL_API_KEY
 * const assessment = await client.kyc.assess('00445790');
 *
 * console.log(assessment.companyName, assessment.riskLevel);
 * ```
 *
 * A key is not always required: reference and lookup endpoints work anonymously
 * at a lower rate limit. Assessments and the AI endpoints always need one.
 *
 * The client holds no connections of its own — it uses the platform `fetch` — so
 * a single long-lived instance per process is the intended usage, and there is
 * nothing to close.
 */
export class KYCCentral {
  private readonly transport: Transport;

  /** Companies House company, officer, PSC, charge and filing data. */
  readonly companies: Companies;
  /** Run risk assessments. */
  readonly kyc: Kyc;
  /** Poll background jobs. `kyc.assess()` uses this for you. */
  readonly jobs: Jobs;
  /** Discover available rule sets. */
  readonly ruleSets: RuleSets;
  /** Discover individual rules and their testable fields. */
  readonly rules: Rules;
  /** Sanctions list screening. */
  readonly sanctions: Sanctions;
  /** Adverse media search. */
  readonly news: News;
  /** ICIJ Offshore Leaks screening. */
  readonly offshoreLeaks: OffshoreLeaks;
  /** GLEIF LEI and parent-chain lookups. */
  readonly gleif: Gleif;
  /** Individual Insolvency Register screening. */
  readonly individualInsolvency: IndividualInsolvency;
  /** Charity Commission lookups. */
  readonly charity: Charity;
  /** HMRC VAT registration lookups. */
  readonly hmrcVat: HmrcVat;
  /** FATF jurisdiction reference data. */
  readonly jurisdictions: Jurisdictions;
  /** Offshore jurisdiction reference data. */
  readonly offshoreJurisdictions: OffshoreJurisdictions;
  /** AI-written analysis. Professional plan. */
  readonly analysis: Analysis;
  /** Product documentation assistant. */
  readonly docs: Docs;
  /** Full report data as JSON. Requires an API key. */
  readonly reports: Reports;

  constructor(options: ClientOptions = {}) {
    this.transport = new Transport(options);

    this.companies = new Companies(this.transport);
    this.kyc = new Kyc(this.transport);
    this.jobs = new Jobs(this.transport);
    this.ruleSets = new RuleSets(this.transport);
    this.rules = new Rules(this.transport);
    this.sanctions = new Sanctions(this.transport);
    this.news = new News(this.transport);
    this.offshoreLeaks = new OffshoreLeaks(this.transport);
    this.gleif = new Gleif(this.transport);
    this.individualInsolvency = new IndividualInsolvency(this.transport);
    this.charity = new Charity(this.transport);
    this.hmrcVat = new HmrcVat(this.transport);
    this.jurisdictions = new Jurisdictions(this.transport);
    this.offshoreJurisdictions = new OffshoreJurisdictions(this.transport);
    this.analysis = new Analysis(this.transport);
    this.docs = new Docs(this.transport);
    this.reports = new Reports(this.transport);
  }

  /** The API root this client talks to. */
  get baseUrl(): string {
    return this.transport.baseUrl;
  }

  /** Whether an API key was resolved. Anonymous clients hit lower rate limits. */
  get isAuthenticated(): boolean {
    return this.transport.isAuthenticated;
  }

  /** Liveness and dependency status. Unversioned, unauthenticated. */
  health(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/health', { versioned: false, signal: options.signal });
  }

  /** Per-upstream availability: Companies House, FCA, GLEIF, sanctions, … */
  dataSourceHealth(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/health/data-sources', {
      versioned: false,
      signal: options.signal,
    });
  }
}
