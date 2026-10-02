# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Changed

- A `Retry-After` longer than 8 seconds is no longer cut to 8 seconds and retried (which
  almost always hit the limit again); the rate-limit error is returned straight away with
  `:retry_after` set.
- POST requests (AI analysis, docs assistant, batch screening) are no longer retried
  after a timeout or a 500/502/504, which could send a billed LLM call more than once.
  They are retried only when the connection was never established, or on 429/503 with
  `Retry-After`.

### Added

- Per-call `:receive_timeout` option on the AI endpoints (`Analysis.company/3`,
  `Analysis.adverse_media_overview/3`, `Analysis.filing_extract/4`, `Docs.ask/3`),
  defaulting to 120 s (or the client timeout, if longer).

### Fixed

- The package no longer lists the test-only `:excoveralls` in `extra_applications`.
  In 0.10.0 this stopped any application depending on `kyccentral` from starting
  (`Could not start application excoveralls`). CI now starts the library from a
  fresh consumer project to catch this class of mistake.

## 0.1.0 — 2026-08-13

First public release.

### Added

- `KYCCentral.new/1` plus resource modules covering every documented `/v1` endpoint:
  `Companies`, `KYC`, `Jobs`, `RuleSets`, `Rules`, `Sanctions`, `News`, `OffshoreLeaks`,
  `FCA`, `GLEIF`, `IndividualInsolvency`, `Charity`, `HMRCVat`, `Jurisdictions`,
  `OffshoreJurisdictions`, `Analysis`, `Docs`, and health.
- `KYCCentral.Assessment` struct with `RiskFlag` and `RuleResult`, atom severities and
  statuses, and helpers: `clear?/1`, `partial?/1`, `flags_at/2`, `flags_at_or_above/2`,
  `has_flag?/2`, `flag/2`, `rules_with_status/2`.
- Transparent polling of queued assessments: a `202 Accepted` job response is polled to
  completion and returned as a finished `Assessment`. Opt out with `wait: false`.
- `KYCCentral.Error`, a single exception struct carrying a `:kind` atom, so failures
  pattern-match without a tree of exception modules. Includes `:retry_after` on rate
  limits and flattened FastAPI validation detail.
- Automatic retries with exponential backoff and jitter for timeouts, connection errors
  and retryable statuses, honouring `Retry-After`. Client errors are never retried.
- Default transport on OTP's `:httpc` with TLS verification configured explicitly
  (`verify_peer`, OS trust store, hostname checking, TLS 1.2/1.3), leaving Jason as the
  only runtime dependency.
- `:http` option to swap in Req, Finch, Tesla or a test stub.
- API key resolution from `KYCCENTRAL_API_KEY`, base URL from `KYCCENTRAL_BASE_URL`.
- Anonymous use for endpoints that permit it, so the library can be tried without an
  account.
