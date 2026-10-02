# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Security

- Redirects are no longer followed. `X-API-Key` is a custom header that the HTTP stack
  forwarded on cross-origin redirects, so a redirect to another host could leak the key.
  A 3xx now raises a status error carrying the `Location` header.

### Removed

- The `KYCCentral.FCA` module (the API now serves `/v1/fca/*` to signed-in sessions
  only, so every call returned 401).

### Changed

- `Companies.advanced_search/2` `:company_status` / `:company_type` / `:sic_codes` take a
  single string (the API never accepted several; a list silently applied one value).
- `Sanctions.screen/3` `:threshold` is an integer 1-100 (documented wrongly as 0-1).
- `Charity.get/3` `:suffix` is an integer.
- Confirming an adverse-media article no longer raises its severity (API behaviour; docs
  corrected).
- An unrecognised severity or risk level now maps to a new `:unknown` level that ranks
  above `:critical`, instead of `:low`, so a value this version doesn't know is never
  filtered out by `flags_at_or_above/2`. The original string is still on `:raw`.
- A `Retry-After` longer than 8 seconds is no longer cut to 8 seconds and retried (which
  almost always hit the limit again); the rate-limit error is returned straight away with
  `:retry_after` set.
- POST requests (AI analysis, docs assistant, batch screening) are no longer retried
  after a timeout or a 500/502/504, which could send a billed LLM call more than once.
  They are retried only when the connection was never established, or on 429/503 with
  `Retry-After`.

### Added

- `unavailable_services` and `psc_chain_depth_capped` on `KYCCentral.Assessment`.
- Five new `KYC.assess/3` options: `:dismissed_media_urls`, `:dismissed_leak_ids`,
  `:confirmed_officer_company_links`, `:confirmed_fca_frn` and `:fca_not_applicable`.
- `Companies.officer_company_matches/2`, `Companies.charge_registrations/2`,
  `Companies.extract_charge_registration/3`, `Analysis.charge_registration/4` and
  `Reports.data/3` (`KYCCentral.Reports`, `POST /billing/report-data`).
- 503 errors carry `:retry_after`, as 429 errors already did.
- Per-call `:receive_timeout` option on the AI endpoints (`Analysis.company/3`,
  `Analysis.adverse_media_overview/3`, `Analysis.filing_extract/4`, `Docs.ask/3`),
  defaulting to 120 s (or the client timeout, if longer).

### Fixed

- `Assessment.partial?/1` now counts `unavailable_services`.
- `:poll_interval`/`:poll_timeout` of zero or less (or not an integer) are rejected up
  front instead of polling the jobs endpoint in a tight loop.
- `KYC.assess(client, "")` (or a whitespace-only company number) now fails validation
  with `:invalid_argument` and makes no request, as in the Python and JavaScript clients.
- A numeric `job_id` in a `202` assessment response is now polled instead of failing
  with `:invalid_argument`.
- Path parameters containing a space are now encoded as `%20` rather than `+`.
- An empty or whitespace-only API key (explicit or from `KYCCENTRAL_API_KEY`) is now
  treated as no key, instead of reporting the client as authenticated while sending no
  key.
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
