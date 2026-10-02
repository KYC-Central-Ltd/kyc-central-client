# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Changed

- POST requests (AI analysis, docs assistant, batch screening) are no longer retried after
  a timeout or a 500/502/504, which could send a billed LLM call more than once. They are
  retried only when the connection was never established, or on 429/503 with Retry-After.

### Added

- Per-call `timeout` option on the AI endpoints, defaulting to 120 s (or the client
  timeout, if longer).

## 0.1.0 — 2026-08-13

First public release.

### Added

- `KYCCentral` and `AsyncKYCCentral` clients covering every documented `/v1` endpoint:
  companies, assessments, rules and rule sets, sanctions, adverse media, offshore leaks,
  FCA, GLEIF, individual insolvency, Charity Commission, HMRC VAT, FATF and offshore
  jurisdictions, AI analysis, the documentation assistant, and health.
- Typed `Assessment`, `RiskFlag` and `RuleResult` models, with severity helpers
  (`critical_flags`, `flags_at_or_above`, `has_flag`) and an `is_partial` check for
  results affected by an upstream timeout.
- Transparent polling of queued assessments: a `202 Accepted` job response is polled to
  completion and returned as a finished `Assessment`. Opt out with `wait=False`.
- Typed exception hierarchy under `KYCCentralError`, with `RateLimitError.retry_after`
  and structured validation errors on `UnprocessableEntityError.body`.
- Automatic retries with exponential backoff and jitter for timeouts, connection errors
  and retryable statuses, honouring `Retry-After`. Client errors are never retried.
- API key resolution from `KYCCENTRAL_API_KEY`, base URL from `KYCCENTRAL_BASE_URL`.
- Anonymous use for endpoints that permit it, so the library can be tried without an
  account.
- Full type hints and a `py.typed` marker.
