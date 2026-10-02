/** Sector registries and jurisdiction reference data. */

import { seg, type Transport } from '../transport.js';
import type { JsonObject } from '../types.js';
import type { CallOptions } from './companies.js';

export interface CharityOptions extends CallOptions {
  /** Linked-charity suffix, an integer. Defaults to 0, the main charity. */
  suffix?: number;
}

/** Charity Commission for England and Wales lookups. */
export class Charity {
  constructor(private readonly transport: Transport) {}

  /** Whether Charity Commission access is configured. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/charity/status', options);
  }

  /** Search registered charities by name. */
  async search(q: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/charity/search', { params: { q }, signal: options.signal });
  }

  /** A charity's register entry. */
  async get(registrationNumber: string, options: CharityOptions = {}): Promise<JsonObject> {
    return this.transport.get(`/charity/charity/${seg(registrationNumber, 'registrationNumber')}`, {
      params: { suffix: options.suffix },
      signal: options.signal,
    });
  }

  /** The charity's registered trustees. */
  async trustees(registrationNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get(
      `/charity/charity/${seg(registrationNumber, 'registrationNumber')}/trustees`,
      options,
    );
  }
}

/** HMRC VAT registration lookups. */
export class HmrcVat {
  constructor(private readonly transport: Transport) {}

  /** Whether HMRC VAT lookups are configured. */
  async status(options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/hmrc-vat/status', options);
  }

  /** Check a UK VAT registration number, with or without the `GB` prefix. */
  async check(vatNumber: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/hmrc-vat/check', {
      params: { vat_number: vatNumber },
      signal: options.signal,
    });
  }
}

/**
 * FATF high-risk and increased-monitoring jurisdiction reference data.
 *
 * Updated after each FATF plenary — roughly February, June and October.
 */
export class Jurisdictions {
  constructor(private readonly transport: Transport) {}

  /** The current FATF black list and grey list. */
  async list(options: CallOptions = {}): Promise<unknown> {
    return this.transport.get('/jurisdictions', options);
  }

  /** Whether one country is FATF-listed, and on which list. */
  async check(country: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/jurisdictions/check', {
      params: { country },
      signal: options.signal,
    });
  }
}

/** Offshore and shell-company jurisdiction reference data. */
export class OffshoreJurisdictions {
  constructor(private readonly transport: Transport) {}

  /** Known offshore jurisdictions and the keywords used to detect them. */
  async list(options: CallOptions = {}): Promise<unknown> {
    return this.transport.get('/offshore-jurisdictions', options);
  }

  /** Whether a name or address indicates an offshore jurisdiction. */
  async check(name: string, options: CallOptions = {}): Promise<JsonObject> {
    return this.transport.get('/offshore-jurisdictions/check', {
      params: { name },
      signal: options.signal,
    });
  }
}
