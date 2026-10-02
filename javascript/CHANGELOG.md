# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Security

- Redirects are no longer followed. `X-API-Key` is a custom header that the HTTP stack
  forwarded on cross-origin redirects, so a redirect to another host could leak the key.
  A 3xx now raises a status error carrying the `Location` header.

### Changed

- An unrecognised severity or risk level now maps to a new `unknown` level that ranks
  above `critical`, instead of `low`, so a value this version doesn't know is never
  filtered out by `flagsAtOrAbove`. The original string is still on `raw`.
- A `Retry-After` longer than 8 seconds is no longer cut to 8 seconds and retried
  (which almost always hit the limit again); the rate-limit error is returned straight
  away with `.retryAfter` set.
- POST requests (AI analysis, docs assistant, batch screening) are no longer retried
  after a timeout or a 500/502/504, which could send a billed LLM call more than once.
  They are retried only when the connection was never established, or on 429/503 with
  `Retry-After`.

### Added

- Per-call `timeoutMs` option on the AI endpoints, defaulting to 120 s (or the client
  timeout, if longer).

## 0.1.0 — 2026-08-13

First public release.

### Added

- `KYCCentral` client covering every documented `/v1` endpoint: companies, assessments,
  rules and rule sets, sanctions, adverse media, offshore leaks, FCA, GLEIF, individual
  insolvency, Charity Commission, HMRC VAT, FATF and offshore jurisdictions, AI analysis,
  the documentation assistant, and health.
- Typed `Assessment`, `RiskFlag` and `RuleResult` shapes, with helper functions
  (`isClear`, `isPartial`, `flagsAt`, `flagsAtOrAbove`, `hasFlag`, `findFlag`) that keep
  the assessment a plain, serialisable object.
- Transparent polling of queued assessments: a `202 Accepted` job response is polled to
  completion and resolved as a finished `Assessment`. Opt out with `wait: false`.
- Typed error hierarchy under `KYCCentralError`, with `RateLimitError.retryAfter` and
  structured validation errors on `UnprocessableEntityError.body`.
- Automatic retries with exponential backoff and jitter for timeouts, connection errors
  and retryable statuses, honouring `Retry-After`. Client errors are never retried, and
  a caller-initiated abort is never retried either.
- `AbortSignal` support on every method, combined with the client's own timeout.
- Custom `fetch` injection for proxying, tracing and tests.
- API key resolution from `KYCCENTRAL_API_KEY`, base URL from `KYCCENTRAL_BASE_URL`,
  guarded so the package still loads in runtimes with no `process`.
- Anonymous use for endpoints that permit it, so the library can be tried without an
  account.
- Zero runtime dependencies; ESM and CJS builds with TypeScript declarations.
