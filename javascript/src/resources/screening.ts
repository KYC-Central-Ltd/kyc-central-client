/** Screening sources: sanctions, adverse media, offshore leaks, GLEIF, insolvency. */

import { namesBody, seg, type Transport } from '../transport.js';
import type { JsonObject } from '../types.js';
import type { CallOptions } from './companies.js';

/** Declared in the API schema for the batch sanctions and offshore-leaks endpoints. */
export const MAX_SCREEN_NAMES = 500;

export interface ScreenOptions extends CallOptions {
  /**
   * Fuzzy-match threshold, an integer from 1 to 100. Overrides the server default;
   * lower values return more, weaker candidates.
   */
  threshold?: number;
  /** Vector-similarity threshold, from 0.0 to 1.0. Overrides the server default. */
  vectorThreshold?: number;
}

export interface EntitiesOptions extends CallOptions {
  /** Substring filter on entity name. */
  search?: string;
  /** e.g. `"person"` or `"organization"`. */
  entityType?: string;
  /** Filter to currently-designated entities. */
  sanctioned?: boolean;
  /** Restrict to one source list, e.g. `"gb_fcdo_sanctions"`. */
  dataset?: string;
  page?: number;
  pageSize?: number;
}

/** An entity with several known names, for {@link News.searchEntities}. */
export interface SearchEntity {
  /** Yours to choose. Echoed back on results, so use it to join onto your records. */
  key: string;
  names: string[];
}

export interface NodeOptions extends CallOptions {
  /** Expected name, used to disambiguate when the id is ambiguous. */
  name?: string;
  /** Expected node type, used the same way. */
  nodeType?: string;
}

function normaliseEntities(entities: readonly SearchEntity[]): { entities: SearchEntity[] } {
  const payload = entities.map((entity) => {
    const key = String(entity?.key ?? '').trim();
    const names = (entity?.names ?? []).map((name) => String(name).trim()).filter(Boolean);
    if (!key) throw new TypeError("each entity needs a non-empty 'key'");
    if (names.length === 0) throw new TypeError(`entity '${key}' needs at least one name`);
    return { key, names };
  });
  if (payload.length === 0) throw new TypeError('entities must contain at least one entry');
  return { entities: payload };
}

/**
 * Screen names against OFAC, the UN Security Council, the UK Sanctions List and
 * the EU Financial Sanctions Files.
 *
 * Matching is approximate — these lists carry transliterated names, aliases and
 * date-of-birth ranges — so treat every hit as a candidate for human review
 * rather than a confirmed match.
 */
export class Sanctions {
  constructor(private readonly transport: Transport) {}

  /** Whether the screening dataset is loaded and ready. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/sanctions/status', options);
  }

  /** Provenance of the loaded lists: sources, publication dates, record counts. */
  async meta(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/sanctions/meta', options);
  }

  /** Screen a single name. */
  async screen(name: string, options: ScreenOptions = {}): Promise<JsonObject> {
    return this.transport.get('/sanctions/screen', {
      params: { name, threshold: options.threshold, vector_threshold: options.vectorThreshold },
      signal: options.signal,
    });
  }

  /**
   * Screen up to 500 names in one request.
   *
   * Far cheaper than a loop over {@link screen}: one request against your rate
   * limit instead of one per name.
   */
  async screenNames(names: readonly string[], options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.post('/sanctions/screen-names', {
      body: namesBody(names, MAX_SCREEN_NAMES),
      signal: options.signal,
    });
  }

  /** Browse the underlying sanctions entities. */
  async entities(options: EntitiesOptions = {}): Promise<JsonObject> {
    return this.transport.get('/sanctions/entities', {
      params: {
        search: options.search,
        entity_type: options.entityType,
        sanctioned: options.sanctioned,
        dataset: options.dataset,
        page: options.page,
        page_size: options.pageSize,
      },
      signal: options.signal,
    });
  }
}

/**
 * Adverse media search. **Requires an active Professional subscription.**
 *
 * Name matching against news results is noisy by nature, so a hit here is a lead
 * to review, not a finding. In an assessment these only raise a low-severity
 * `ADVERSE_MEDIA_UNCONFIRMED` flag until an analyst confirms the article.
 */
export class News {
  constructor(private readonly transport: Transport) {}

  /** Whether adverse media search is configured and available. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/news/status', options);
  }

  /**
   * Search adverse media for a batch of names.
   *
   * The per-request cap is set server-side and can be tuned by the operator, so
   * a large batch may be rejected with a 422.
   */
  async searchNames(names: readonly string[], options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.post('/news/search-names', {
      body: namesBody(names),
      signal: options.signal,
    });
  }

  /** Search adverse media for entities that each have several known names. */
  async searchEntities(
    entities: readonly SearchEntity[],
    options: CallOptions = {},
  ): Promise<JsonObject> {
    return this.transport.post('/news/search-entities', {
      body: normaliseEntities(entities),
      signal: options.signal,
    });
  }

  /** Search adverse media for a company and its officers and PSCs. */
  async screenCompany(companyNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/news/screen-company', {
      params: { company_number: seg(companyNumber, 'companyNumber') },
      signal: options.signal,
    });
  }
}

/**
 * Screen against the ICIJ Offshore Leaks database.
 *
 * Covers the Panama, Paradise and Pandora Papers plus the Offshore Leaks and
 * Bahamas Leaks datasets. As with adverse media, matches are name-based and
 * unconfirmed hits only raise a low-severity flag in an assessment.
 */
export class OffshoreLeaks {
  constructor(private readonly transport: Transport) {}

  /** Whether the Offshore Leaks dataset is available. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/offshore-leaks/status', options);
  }

  /** Screen up to 500 names against the leaks datasets. */
  async screenNames(names: readonly string[], options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.post('/offshore-leaks/screen-names', {
      body: namesBody(names, MAX_SCREEN_NAMES),
      signal: options.signal,
    });
  }

  /** Screen a company and its officers and PSCs against the leaks datasets. */
  async screenCompany(companyNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/offshore-leaks/screen-company', {
      params: { company_number: seg(companyNumber, 'companyNumber') },
      signal: options.signal,
    });
  }

  /** Fetch one leaks node — an entity, officer, intermediary or address. */
  async node(nodeId: string, options: NodeOptions = {}): Promise<JsonObject> {
    return this.transport.get(`/offshore-leaks/node/${seg(nodeId, 'nodeId')}`, {
      params: { name: options.name, node_type: options.nodeType },
      signal: options.signal,
    });
  }
}

/** Global LEI Foundation lookups — legal entity identifiers and parent chains. */
export class Gleif {
  constructor(private readonly transport: Transport) {}

  /** The company's LEI record and its direct and ultimate parents. */
  async company(companyNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/gleif/company', {
      params: { company_number: seg(companyNumber, 'companyNumber') },
      signal: options.signal,
    });
  }
}

/** Insolvency Service Individual Insolvency Register screening. */
export class IndividualInsolvency {
  constructor(private readonly transport: Transport) {}

  /** Check a company's officers and PSCs for personal insolvency records. */
  async screenCompany(companyNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/individual-insolvency/screen-company', {
      params: { company_number: seg(companyNumber, 'companyNumber') },
      signal: options.signal,
    });
  }
}
