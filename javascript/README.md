<div align="center">

# KYC Central — JavaScript & TypeScript client

**UK company KYC and AML risk assessment, from one API call.**

[![npm](https://img.shields.io/npm/v/@kyccentral/sdk.svg)](https://www.npmjs.com/package/@kyccentral/sdk)
[![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-javascript.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-javascript.yml)
[![Types](https://img.shields.io/npm/types/@kyccentral/sdk.svg)](https://www.npmjs.com/package/@kyccentral/sdk)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Website](https://kyccentral.co.uk) · [API reference](https://kyccentral.co.uk/api-docs) · [Get an API key](https://kyccentral.co.uk/account) · [Other clients](#other-languages)

</div>

---

Screen a UK company against Companies House, the FCA Register, GLEIF, the Insolvency
Service, OFAC / UN / UK / EU sanctions lists, adverse media and the ICIJ Offshore Leaks
database — then run a configurable rule engine over the result and get back a structured
list of risk flags.

```ts
import { KYCCentral, flagsAtOrAbove } from '@kyccentral/sdk';

const client = new KYCCentral(); // reads KYCCENTRAL_API_KEY
const assessment = await client.kyc.assess('00445790');

console.log(assessment.companyName, '→', assessment.riskLevel);
for (const flag of flagsAtOrAbove(assessment, 'high')) {
  console.log(`  [${flag.severity}] ${flag.code}: ${flag.description}`);
}
```

```
TESCO PLC → medium
  [high] ACCOUNTS_OVERDUE: Annual accounts are 42 days overdue.
```

**Zero runtime dependencies.** Built on the platform `fetch`, so it runs unchanged on
Node 18+, Deno, Bun, Cloudflare Workers, Vercel Edge and the browser. Ships ESM and CJS
builds with full TypeScript types.

## Contents

- [Install](#install)
- [Authentication](#authentication)
- [Quick start](#quick-start)
- [Working with an assessment](#working-with-an-assessment)
- [Error handling](#error-handling)
- [Retries, timeouts and cancellation](#retries-timeouts-and-cancellation)
- [Rate limits and plans](#rate-limits-and-plans)
- [API coverage](#api-coverage)
- [Using it in the browser](#using-it-in-the-browser)
- [Compliance notes](#compliance-notes)
- [Contributing](#contributing)

## Install

```bash
npm install @kyccentral/sdk
```

```bash
pnpm add @kyccentral/sdk    # or: yarn add @kyccentral/sdk
```

Requires Node 18 or later (or any runtime with a global `fetch`).

## Authentication

Generate a key in [Account settings](https://kyccentral.co.uk/account), then either set
an environment variable:

```bash
export KYCCENTRAL_API_KEY="your_key"
```

```ts
const client = new KYCCentral();
```

…or pass it explicitly:

```ts
const client = new KYCCentral({ apiKey: 'your_key' });
```

**A key is not always required.** Reference and lookup endpoints — company search,
sanctions screening, FATF jurisdictions, health — work anonymously at a lower rate
limit, which makes the library easy to try before you sign up. Assessments
(`client.kyc.assess`) and the AI endpoints always need a key.

## Quick start

```ts
import { KYCCentral, isPartial } from '@kyccentral/sdk';

const client = new KYCCentral();

// 1. Find the company
const results = await client.companies.search('tesco plc', { itemsPerPage: 5 });
const companyNumber = results.items[0].company_number;

// 2. Assess it
const assessment = await client.kyc.assess(companyNumber);

// 3. Act on the result
const critical = assessment.flags.filter((f) => f.severity === 'critical');
if (critical.length > 0) {
  console.log(
    'BLOCK — critical findings:',
    critical.map((f) => f.code),
  );
} else if (assessment.riskLevel === 'low' && !isPartial(assessment)) {
  console.log('Clear to onboard.');
} else {
  console.log('Refer for manual review.');
}
```

The client holds no connections of its own, so there is nothing to close. Construct one
per process and reuse it.

## Working with an assessment

`assess()` resolves to a typed `Assessment`, with camel-cased fields:

```ts
assessment.companyName; // "TESCO PLC"
assessment.riskLevel; // "medium"
assessment.flags; // [{ code: "ACCOUNTS_OVERDUE", severity: "high", description, raw }]
assessment.ruleResults; // every rule, including the ones that passed (each has `raw` too)
assessment.checkedAt; // when this assessment ran
assessment.dataFetchedAt; // how fresh the underlying registry data is
```

Severities and risk levels are `'low'`, `'medium'`, `'high'`, `'critical'` or
`'unknown'`. `'unknown'` is a value this client version doesn't recognise; it ranks
above `'critical'` so `flagsAtOrAbove` never filters it out, and the original string is
on `raw`.

Helper functions keep the common checks short. They're free functions rather than
methods, so an `Assessment` stays a plain object — safe to put in React state, pass
through `structuredClone`, or `JSON.stringify` and back:

```ts
import { isClear, isPartial, flagsAt, flagsAtOrAbove, hasFlag, findFlag } from '@kyccentral/sdk';

isClear(assessment); // no flags at all
flagsAt(assessment, 'critical'); // blockers
flagsAtOrAbove(assessment, 'high'); // by severity
hasFlag(assessment, 'ACCOUNTS_OVERDUE'); // by code
findFlag(assessment, 'PSC_CHAIN_TOO_DEEP'); // -> RiskFlag | undefined
```

The evidence each rule was judged against is on the `*Summary` fields —
`officersSummary`, `pscSummary`, `sanctionsSummary`, `chargesSummary` and so on — and
the untouched response body is always on `assessment.raw`, so a field this client
version doesn't model yet is never lost.

### Partial results are marked as partial

An assessment fans out to a dozen upstream sources. When one is slow or down, the API
returns what it has and says so rather than silently reporting a clean result:

```ts
if (isPartial(assessment)) {
  console.warn('Incomplete:', assessment.timedOutServices, assessment.failedRules);
}
```

**Treat `isPartial` as "not yet screened", not "clean".** An absent flag from a source
that timed out is not evidence of absence.

### Confirming noisy matches

Adverse media and Offshore Leaks matching is fuzzy, so unconfirmed hits only ever raise
a low-severity `*_UNCONFIRMED` flag. Once an analyst has confirmed a specific article or
match, pass it back to promote it to full severity:

```ts
await client.kyc.assess('00445790', {
  confirmedMediaUrls: ['https://news.example/article'],
  confirmedLeakIds: ['icij-node-12345'],
});
```

### Queued assessments are handled for you

A cold assessment can take longer than a sensible HTTP timeout, so the API may answer
`202 Accepted` with a job id instead of holding the connection open. This client polls
the job and resolves with the finished assessment either way:

```ts
await client.kyc.assess('00445790'); // resolves when done
await client.kyc.assess('00445790', { pollTimeoutMs: 300_000 }); // allow longer
await client.kyc.assess('00445790', { wait: false }); // { job_id, status }
```

## Error handling

Every error inherits from `KYCCentralError`, so one `catch` handles transport failures
and API errors alike:

```ts
import {
  KYCCentralError,
  AuthenticationError,
  PermissionDeniedError,
  NotFoundError,
  RateLimitError,
  APIConnectionError,
} from '@kyccentral/sdk';

try {
  const assessment = await client.kyc.assess('00445790');
} catch (error) {
  if (error instanceof NotFoundError) {
    console.log('No such company.');
  } else if (error instanceof PermissionDeniedError) {
    console.log('Plan does not cover this:', error.detail); // usually needs Professional
  } else if (error instanceof RateLimitError) {
    console.log('Slow down — retry in', error.retryAfter, 'seconds');
  } else if (error instanceof AuthenticationError) {
    console.log('Check KYCCENTRAL_API_KEY.');
  } else if (error instanceof APIConnectionError) {
    console.log('Network problem reaching the API.');
  } else if (error instanceof KYCCentralError) {
    console.log('Unexpected API failure:', error.message);
  } else {
    throw error;
  }
}
```

| Class                                     | Status | Usual cause                                          |
| ----------------------------------------- | ------ | ---------------------------------------------------- |
| `BadRequestError`                         | 400    | Malformed request                                    |
| `AuthenticationError`                     | 401    | Missing or invalid API key                           |
| `PermissionDeniedError`                   | 403    | Endpoint needs an active Professional subscription   |
| `NotFoundError`                           | 404    | No such company, officer, charge, rule or rule set   |
| `UnprocessableEntityError`                | 422    | Failed the API's validation — see `.body`            |
| `RateLimitError`                          | 429    | Rate limit or monthly free quota — see `.retryAfter` |
| `ServerError` / `ServiceUnavailableError` | 5xx    | API or an upstream dependency failed                 |
| `APIConnectionError` / `APITimeoutError`  | —      | Never reached the API                                |
| `JobFailedError` / `JobTimeoutError`      | —      | A queued assessment failed or outran `pollTimeoutMs` |

Every `APIStatusError` carries `.statusCode`, `.detail`, `.body` and `.headers`.

Argument validation rejects rather than throwing synchronously, so a single `.catch()`
covers every failure mode:

```ts
client.sanctions.screenNames([]).catch((error) => console.log(error.message));
```

## Retries, timeouts and cancellation

GET requests retry timeouts, connection failures and retryable statuses (408, 429, 500,
502, 503, 504) twice by default, with exponential backoff plus jitter, honouring
`Retry-After`. POST requests (the AI endpoints, the docs assistant and batch screening)
are retried only when the connection was never established, or on 429/503 with a
`Retry-After` header, so a slow AI call is never sent twice. Client errors like 401, 403,
404 and 422 are never retried.

A `Retry-After` longer than 8 seconds is not waited out; the client surfaces the
rate-limit error immediately with `.retryAfter` set so you can schedule the retry.

The AI endpoints (`analysis.company`, `analysis.adverseMediaOverview`,
`analysis.filingExtract`, `docs.ask`) default to a 120 s timeout, or the client's
`timeoutMs` if that is longer. Override it per call:

```ts
await client.analysis.company('00445790', { timeoutMs: 180_000 });
```

```ts
const client = new KYCCentral({
  timeoutMs: 60_000, // per-request
  maxRetries: 5, // 0 disables retries entirely
});
```

Every method accepts an `AbortSignal`. A caller-initiated abort is never retried:

```ts
const controller = new AbortController();
setTimeout(() => controller.abort(), 5_000);

await client.companies.dossier('00445790', { signal: controller.signal });
```

Supply your own `fetch` for proxying, tracing or tests:

```ts
const client = new KYCCentral({
  fetch: (url, init) => {
    console.log('→', url);
    return fetch(url, init);
  },
});
```

The client never follows redirects (it passes `redirect: 'manual'`), so the API key is
never sent to another host; a 3xx surfaces as an `APIStatusError` with the `Location`
header. If you supply your own `fetch`, make sure it does not follow redirects, or at
least does not forward `X-API-Key` to another origin.

## Rate limits and plans

| Tier                      | Limit                                            |
| ------------------------- | ------------------------------------------------ |
| Anonymous                 | 30 requests / minute, per IP                     |
| Authenticated             | 120 requests / minute                            |
| Professional subscription | 60 assessments / minute, full endpoint access    |
| Free plan                 | A fixed number of assessments per calendar month |

Cached results and failed runs don't consume free-plan quota. Endpoints marked
**Professional** below reject with `PermissionDeniedError` without an active
subscription.

Batch endpoints exist precisely to stay inside these limits —
`client.sanctions.screenNames([...])` screens up to 500 names in a single request.

## API coverage

Every documented endpoint is available.

<details>
<summary><b>Companies</b> — <code>client.companies</code></summary>

| Method                                             | Endpoint                                                         |
| -------------------------------------------------- | ---------------------------------------------------------------- |
| `search(q, opts?)`                                 | `GET /companies/search`                                          |
| `searchOfficers(q, opts?)`                         | `GET /companies/search/officers`                                 |
| `advancedSearch(opts?)`                            | `GET /companies/advanced-search`                                 |
| `get(companyNumber)`                               | `GET /companies/{n}`                                             |
| `dossier(n)`                                       | `GET /companies/{n}/dossier`                                     |
| `officers(n)`                                      | `GET /companies/{n}/officers`                                    |
| `pscs(n)`                                          | `GET /companies/{n}/persons-with-significant-control`            |
| `pscStatements(n)`                                 | `GET /companies/{n}/persons-with-significant-control-statements` |
| `pscChainDepth(n)`                                 | `GET /companies/{n}/psc-chain-depth`                             |
| `pscChainTree(n)`                                  | `GET /companies/{n}/psc-chain-tree`                              |
| `charges(n)`                                       | `GET /companies/{n}/charges`                                     |
| `charge(n, chargeId)`                              | `GET /companies/{n}/charges/{id}`                                |
| `insolvency(n)`                                    | `GET /companies/{n}/insolvency`                                  |
| `disqualifications(n)`                             | `GET /companies/{n}/disqualifications`                           |
| `officerDisqualification(n, officerId)`            | `GET /companies/{n}/officers/{id}/disqualification`              |
| `officerAppointments(officerId, opts?)`            | `GET /companies/officers/{id}/appointments`                      |
| `filingHistory(n, opts?)` **Professional**         | `GET /companies/{n}/filing-history`                              |
| `filingExtract(n, transactionId)` **Professional** | `GET /companies/{n}/filing-history/{tx}/extract`                 |
| `statementOfCapital(n)` **Professional**           | `GET /companies/{n}/statement-of-capital`                        |

`dossier()` returns profile, officers, PSCs, charges, insolvency and filings in one
request — cheaper than six separate calls.

</details>

<details>
<summary><b>Assessments and rules</b> — <code>client.kyc</code>, <code>client.ruleSets</code>, <code>client.rules</code></summary>

| Method                                      | Endpoint            |
| ------------------------------------------- | ------------------- |
| `kyc.assess(companyNumber \| { q }, opts?)` | `GET /kyc/assess`   |
| `ruleSets.list()`                           | `GET /rule-sets`    |
| `rules.list()`                              | `GET /rules`        |
| `rules.fields()`                            | `GET /rules/fields` |
| `jobs.get(jobId)`                           | `GET /jobs/{id}`    |

</details>

<details>
<summary><b>Screening</b> — <code>client.sanctions</code>, <code>client.news</code>, <code>client.offshoreLeaks</code></summary>

| Method                                      | Endpoint                             |
| ------------------------------------------- | ------------------------------------ |
| `sanctions.status()`                        | `GET /sanctions/status`              |
| `sanctions.meta()`                          | `GET /sanctions/meta`                |
| `sanctions.screen(name, opts?)`             | `GET /sanctions/screen`              |
| `sanctions.screenNames([…])`                | `POST /sanctions/screen-names`       |
| `sanctions.entities(opts?)`                 | `GET /sanctions/entities`            |
| `news.status()`                             | `GET /news/status`                   |
| `news.searchNames([…])` **Professional**    | `POST /news/search-names`            |
| `news.searchEntities([…])` **Professional** | `POST /news/search-entities`         |
| `news.screenCompany(n)` **Professional**    | `GET /news/screen-company`           |
| `offshoreLeaks.status()`                    | `GET /offshore-leaks/status`         |
| `offshoreLeaks.screenNames([…])`            | `POST /offshore-leaks/screen-names`  |
| `offshoreLeaks.screenCompany(n)`            | `GET /offshore-leaks/screen-company` |
| `offshoreLeaks.node(nodeId, opts?)`         | `GET /offshore-leaks/node/{id}`      |

Sanctions coverage: OFAC (US), UN Security Council, the UK Sanctions List and the EU
Financial Sanctions Files.

</details>

<details>
<summary><b>Registries</b> — <code>client.fca</code>, <code>client.gleif</code>, <code>client.individualInsolvency</code>, <code>client.charity</code>, <code>client.hmrcVat</code></summary>

| Method                                  | Endpoint                                    |
| --------------------------------------- | ------------------------------------------- |
| `fca.status()`                          | `GET /fca/status`                           |
| `fca.search(q)`                         | `GET /fca/search`                           |
| `fca.firm(frn)`                         | `GET /fca/firm/{frn}`                       |
| `fca.firmNames(frn)`                    | `GET /fca/firm/{frn}/names`                 |
| `fca.firmIndividuals(frn)`              | `GET /fca/firm/{frn}/individuals`           |
| `fca.screenIndividuals(n)`              | `GET /fca/screen-individuals`               |
| `fca.checkIndividual(name)`             | `GET /fca/check-individual`                 |
| `gleif.company(n)`                      | `GET /gleif/company`                        |
| `individualInsolvency.screenCompany(n)` | `GET /individual-insolvency/screen-company` |
| `charity.status()`                      | `GET /charity/status`                       |
| `charity.search(q)`                     | `GET /charity/search`                       |
| `charity.get(regno, opts?)`             | `GET /charity/charity/{regno}`              |
| `charity.trustees(regno)`               | `GET /charity/charity/{regno}/trustees`     |
| `hmrcVat.status()`                      | `GET /hmrc-vat/status`                      |
| `hmrcVat.check(vatNumber)`              | `GET /hmrc-vat/check`                       |

</details>

<details>
<summary><b>Reference data, AI analysis and health</b></summary>

| Method                                                     | Endpoint                                |
| ---------------------------------------------------------- | --------------------------------------- |
| `jurisdictions.list()`                                     | `GET /jurisdictions`                    |
| `jurisdictions.check(country)`                             | `GET /jurisdictions/check`              |
| `offshoreJurisdictions.list()`                             | `GET /offshore-jurisdictions`           |
| `offshoreJurisdictions.check(name)`                        | `GET /offshore-jurisdictions/check`     |
| `analysis.status()`                                        | `GET /analysis/status`                  |
| `analysis.company(n, opts?)` **Professional**              | `POST /analysis/company`                |
| `analysis.adverseMediaOverview(n, opts?)` **Professional** | `POST /analysis/adverse-media-overview` |
| `analysis.filingExtract(n, tx, opts?)`                     | `POST /analysis/filing-extract`         |
| `docs.ask(message, opts?)`                                 | `POST /docs/ask`                        |
| `client.health()`                                          | `GET /health`                           |
| `client.dataSourceHealth()`                                | `GET /health/data-sources`              |

FATF listings are refreshed after each plenary (roughly February, June and October).

</details>

Endpoints that proxy an upstream registry return the decoded JSON as `JsonObject`, so
new upstream fields reach you the day they ship instead of waiting on a client release.
The assessment result — the one response shape this API owns — is fully typed.

## Using it in the browser

The client works in the browser, but **do not ship your API key to it**. A key in
front-end code is public, and anyone who reads it can spend your quota. Call the API from
your own server, or put a thin proxy in front of it and point the client at that:

```ts
const client = new KYCCentral({ baseUrl: 'https://your-app.example/api/kyc-proxy' });
```

## Compliance notes

This library is a client for a data API. It is not, and does not provide, regulatory
advice, and using it does not by itself discharge any obligation under the Money
Laundering Regulations.

- **Sanctions and adverse media matching is approximate.** Sanctions lists carry
  transliterated names, aliases and date-of-birth ranges. Every hit is a candidate for
  human review, not a determination.
- **Unconfirmed matches are deliberately low-severity.** Adverse media and Offshore
  Leaks hits stay at `*_UNCONFIRMED` until an analyst confirms the specific article or
  match. Don't promote them programmatically.
- **There is no PEP screening.** The platform ingests sanctions lists only. Nothing here
  identifies politically exposed persons.
- **Check `isPartial()` before recording a clean result.** See
  [Partial results](#partial-results-are-marked-as-partial).
- **Registry data has a lag.** `assessment.dataFetchedAt` tells you how fresh the
  underlying Companies House data is.

## Other languages

| Language                | Package                                                            | Repository                                                         |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| Python                  | [`kyccentral`](https://pypi.org/project/kyccentral/)               | [kyccentral-python](https://github.com/qualia91/kyccentral-python) |
| JavaScript / TypeScript | [`@kyccentral/sdk`](https://www.npmjs.com/package/@kyccentral/sdk) | [kyccentral-js](https://github.com/qualia91/kyccentral-js)         |
| Elixir / Erlang         | [`kyccentral`](https://hex.pm/packages/kyccentral)                 | [kyccentral-elixir](https://github.com/qualia91/kyccentral-elixir) |

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/qualia91/kyccentral-js
cd kyccentral-js
npm install
npm test
```

The test suite mocks `fetch`, so it runs offline and needs no API key.

## Licence

[MIT](LICENSE) © KYC Central
