# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 0.11.0 — 2026-10-02

### Security

- Redirects are no longer followed. `X-API-Key` is a custom header that the HTTP stack
  forwarded on cross-origin redirects, so a redirect to another host could leak the key. A
  3xx now raises a status error carrying the `Location` header.

### Removed

- The `fca` namespace (`client.fca`, `Fca`, `AsyncFca`): the API now serves `/v1/fca/*` to
  signed-in sessions only, so every call returned 401.

### Changed

- Advanced-search `company_status` / `company_type` / `sic_codes` take a single string (the
  API never accepted several; a list silently applied one value).
- `sanctions.screen` `threshold` is an integer from 1 to 100 (it was documented wrongly as
  0-1).
- `charity.get` `suffix` is an integer.
- Confirming an adverse-media article no longer raises its severity (API behaviour; docs
  corrected).
- An unrecognised severity or risk level now maps to a new `unknown` level that ranks above
  `critical`, instead of `low`, so a value this version doesn't know is never filtered out
  by `flags_at_or_above`. The original string is still on `raw`.
- A `Retry-After` longer than 8 seconds is no longer cut to 8 seconds and retried (which
  almost always hit the limit again); the rate-limit error is returned straight away with
  `.retry_after` set.
- POST requests (AI analysis, docs assistant, batch screening) are no longer retried after
  a timeout or a 500/502/504, which could send a billed LLM call more than once. They are
  retried only when the connection was never established, or on 429/503 with Retry-After.

### Added

- `unavailable_services` and `psc_chain_depth_capped` on the assessment.
- Five new `kyc.assess` options: `dismissed_media_urls`, `dismissed_leak_ids`,
  `confirmed_officer_company_links`, `confirmed_fca_frn` and `fca_not_applicable`.
- `companies.officer_company_matches`, `companies.charge_registrations`,
  `companies.extract_charge_registration` (Professional), `analysis.charge_registration`
  and `reports.data`.
- `ServiceUnavailableError.retry_after`, parsed from the `Retry-After` header like
  `RateLimitError.retry_after`.
- Per-call `timeout` option on the AI endpoints, defaulting to 120 s (or the client
  timeout, if longer).

### Fixed

- `Assessment.is_partial` now counts `unavailable_services`.
- A clean `Assessment` (no flags) is now truthy; `__len__` made it falsy, so
  `if assessment:` misfired.
- An empty or whitespace-only API key (explicit or from `KYCCENTRAL_API_KEY`) is now treated
  as no key, instead of reporting the client as authenticated while sending no key.
- `poll_interval`/`poll_timeout` of zero or less are rejected up front instead of polling
  the jobs endpoint in a tight loop.

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
