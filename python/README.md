<div align="center">

# KYC Central — Python client

**UK company KYC and AML risk assessment, from one API call.**

[![PyPI](https://img.shields.io/pypi/v/kyccentral.svg)](https://pypi.org/project/kyccentral/)
[![Python versions](https://img.shields.io/pypi/pyversions/kyccentral.svg)](https://pypi.org/project/kyccentral/)
[![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-python.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-python.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Website](https://kyccentral.co.uk) · [API reference](https://kyccentral.co.uk/api-docs) · [Get an API key](https://kyccentral.co.uk/account) · [Other clients](#other-languages)

</div>

---

Screen a UK company against Companies House, the FCA Register, GLEIF, the Insolvency
Service, OFAC / UN / UK / EU sanctions lists, adverse media and the ICIJ Offshore Leaks
database — then run a configurable rule engine over the result and get back a structured
list of risk flags.

```python
from kyccentral import KYCCentral, RiskLevel

client = KYCCentral()  # reads KYCCENTRAL_API_KEY
assessment = client.kyc.assess("00445790")

print(assessment.company_name, "→", assessment.risk_level.value)
for flag in assessment.flags_at_or_above(RiskLevel.HIGH):
    print(f"  [{flag.severity.value}] {flag.code}: {flag.description}")
```

```
TESCO PLC → medium
  [high] ACCOUNTS_OVERDUE: Annual accounts are 42 days overdue.
```

## Contents

- [Install](#install)
- [Authentication](#authentication)
- [Quick start](#quick-start)
- [Working with an assessment](#working-with-an-assessment)
- [Async](#async)
- [Error handling](#error-handling)
- [Retries and timeouts](#retries-and-timeouts)
- [Rate limits and plans](#rate-limits-and-plans)
- [API coverage](#api-coverage)
- [Compliance notes](#compliance-notes)
- [Contributing](#contributing)

## Install

```bash
pip install kyccentral
```

Requires Python 3.10+. The only dependency is [`httpx`](https://www.python-httpx.org/).

## Authentication

Generate a key in [Account settings](https://kyccentral.co.uk/account), then either set
an environment variable:

```bash
export KYCCENTRAL_API_KEY="your_key"
```

```python
client = KYCCentral()
```

…or pass it explicitly:

```python
client = KYCCentral(api_key="your_key")
```

**A key is not always required.** Reference and lookup endpoints — company search,
sanctions screening, FATF jurisdictions, health — work anonymously at a lower rate
limit, which makes the library easy to try before you sign up. Assessments
(`client.kyc.assess`) and the AI endpoints always need a key.

## Quick start

```python
from kyccentral import KYCCentral, RiskLevel

with KYCCentral() as client:
    # 1. Find the company
    results = client.companies.search("tesco plc", items_per_page=5)
    company_number = results["items"][0]["company_number"]

    # 2. Assess it
    assessment = client.kyc.assess(company_number)

    # 3. Act on the result
    if assessment.critical_flags:
        print("BLOCK — critical findings:")
        for flag in assessment.critical_flags:
            print(" ", flag.code, flag.description)
    elif assessment.risk_level is RiskLevel.LOW and not assessment.is_partial:
        print("Clear to onboard.")
    else:
        print("Refer for manual review.")
```

Using the client as a context manager (or calling `client.close()`) returns its
connection pool. A long-lived client is fine and preferred — construct one per process,
not one per request.

## Working with an assessment

`assess()` returns a typed [`Assessment`](src/kyccentral/models.py):

```python
assessment.company_name  # "TESCO PLC"
assessment.risk_level  # RiskLevel.MEDIUM
assessment.flags  # [RiskFlag(code="ACCOUNTS_OVERDUE", ...), ...]
assessment.rule_results  # every rule, including the ones that passed
assessment.checked_at  # when this assessment ran
assessment.data_fetched_at  # how fresh the underlying registry data is
```

Convenience accessors keep the common checks short:

```python
assessment.is_clear  # no flags at all
assessment.critical_flags  # blockers
assessment.flags_at_or_above(RiskLevel.HIGH)  # by severity
assessment.has_flag("ACCOUNTS_OVERDUE")  # by code
assessment.flag("PSC_CHAIN_TOO_DEEP")  # -> RiskFlag | None

len(assessment)  # number of flags
for flag in assessment:
    ...  # iterates flags
```

Severities are `RiskLevel.LOW`, `MEDIUM`, `HIGH` and `CRITICAL`, plus `RiskLevel.UNKNOWN` for a
value this client version does not recognise. `UNKNOWN` ranks above `CRITICAL`, so it is never
filtered out by `flags_at_or_above`; the original string is on `flag.raw`.

The evidence each rule was judged against is on the `*_summary` attributes —
`officers_summary`, `psc_summary`, `sanctions_summary`, `charges_summary` and so on —
and the untouched response body is always on `assessment.raw`, so a field this client
version doesn't model yet is never lost.

### Partial results are marked as partial

An assessment fans out to a dozen upstream sources. When one is slow or down, the API
returns what it has and says so rather than silently reporting a clean result:

```python
if assessment.is_partial:
    print("Incomplete:", assessment.timed_out_services, assessment.failed_rules)
```

**Treat `is_partial` as "not yet screened", not "clean".** An absent flag from a source
that timed out is not evidence of absence.

### Confirming noisy matches

Adverse media and Offshore Leaks matching is fuzzy, so unconfirmed hits only ever raise
a low-severity `*_UNCONFIRMED` flag. Once an analyst has confirmed a specific article or
match, pass it back to promote it to full severity:

```python
assessment = client.kyc.assess(
    "00445790",
    confirmed_media_urls=["https://news.example/article"],
    confirmed_leak_ids=["icij-node-12345"],
)
```

### Queued assessments are handled for you

A cold assessment can take longer than a sensible HTTP timeout, so the API may answer
`202 Accepted` with a job id instead of holding the connection open. This client polls
the job and returns the finished assessment either way — you don't have to care:

```python
assessment = client.kyc.assess("00445790")  # blocks until done
assessment = client.kyc.assess("00445790", poll_timeout=300)  # allow longer
job = client.kyc.assess("00445790", wait=False)  # {"job_id": ..., "status": ...}
```

## Async

`AsyncKYCCentral` mirrors the sync client exactly — same namespaces, same method names,
same arguments:

```python
import asyncio
from kyccentral import AsyncKYCCentral


async def main():
    async with AsyncKYCCentral() as client:
        numbers = ["00445790", "02627406", "03824658"]
        assessments = await asyncio.gather(*(client.kyc.assess(n) for n in numbers))
        for a in assessments:
            print(a.company_name, a.risk_level.value, len(a.flags))


asyncio.run(main())
```

## Error handling

Every error inherits from `KYCCentralError`, so one `except` catches transport failures
and API errors alike. Catch the narrower types when you want to react differently:

```python
from kyccentral import (
    KYCCentral,
    KYCCentralError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    RateLimitError,
    APIConnectionError,
)

try:
    assessment = client.kyc.assess("00445790")
except NotFoundError:
    print("No such company.")
except PermissionDeniedError as exc:
    print("Plan does not cover this:", exc.detail)  # usually needs Professional
except RateLimitError as exc:
    print("Slow down — retry in", exc.retry_after, "seconds")
except AuthenticationError:
    print("Check KYCCENTRAL_API_KEY.")
except APIConnectionError:
    print("Network problem reaching the API.")
except KYCCentralError as exc:
    print("Unexpected API failure:", exc)
```

| Exception | Status | Usual cause |
|---|---|---|
| `BadRequestError` | 400 | Malformed request |
| `AuthenticationError` | 401 | Missing or invalid API key |
| `PermissionDeniedError` | 403 | Endpoint needs an active Professional subscription |
| `NotFoundError` | 404 | No such company, officer, charge, rule or rule set |
| `UnprocessableEntityError` | 422 | Failed the API's validation — see `.body` |
| `RateLimitError` | 429 | Rate limit or monthly free quota hit — see `.retry_after` |
| `ServerError` / `ServiceUnavailableError` | 5xx | API or an upstream dependency failed |
| `APIConnectionError` / `APITimeoutError` | — | Never reached the API |
| `JobFailedError` / `JobTimeoutError` | — | A queued assessment failed or outran `poll_timeout` |

Every `APIStatusError` carries `.status_code`, `.detail`, `.body` and `.headers`.

## Retries and timeouts

GETs retry timeouts, connection failures and retryable statuses (408, 429, 500, 502, 503,
504) twice by default, with exponential backoff plus jitter, honouring `Retry-After`.
POSTs are retried only when the connection was never established, or on 429/503 with a
`Retry-After` header, so a slow AI call is never sent twice. A `Retry-After` longer than
8 seconds is not waited out; the rate-limit error is returned immediately with
`.retry_after` set, so you can schedule the retry yourself. Client errors like 401, 403,
404 and 422 are never retried — they will not become true on a second attempt.

The AI endpoints (`analysis.company`, `analysis.adverse_media_overview`,
`analysis.filing_extract`, `docs.ask`) wait up to 120 seconds by default, or the client
timeout if that is longer. Override it per call:

```python
client.analysis.company("00445790", timeout=240.0)  # seconds, this call only
```

```python
client = KYCCentral(
    timeout=60.0,  # per-request, seconds
    max_retries=5,  # 0 disables retries entirely
)
```

Bring your own transport for a shared pool, a proxy, or custom TLS:

```python
import httpx

client = KYCCentral(http_client=httpx.Client(proxy="http://proxy.internal:8080"))
```

The `timeout` argument is ignored when `http_client` is supplied; configure the timeout on
that client. The per-call `timeout` on the AI endpoints still applies.

You keep ownership of a client you supply — this library will not close it. The client
it builds itself never follows redirects, so the API key is never sent to another host; a
3xx surfaces as an `APIStatusError` with the `Location` header. If you supply your own
`httpx` client, make sure it does not follow redirects (the httpx default) or at least does
not forward `X-API-Key` to another origin.

## Rate limits and plans

| Tier | Limit |
|---|---|
| Anonymous | 30 requests / minute, per IP |
| Authenticated | 120 requests / minute |
| Professional subscription | 60 assessments / minute, full endpoint access |
| Free plan | A fixed number of assessments per calendar month |

Cached results and failed runs don't consume free-plan quota. Endpoints marked
**Professional** below raise `PermissionDeniedError` without an active subscription.

Batch endpoints exist precisely to stay inside these limits — `client.sanctions.screen_names([...])`
screens up to 500 names against a single request rather than 500.

## API coverage

Every documented endpoint is available. Each namespace has an identical `Async` twin.

<details>
<summary><b>Companies</b> — <code>client.companies</code></summary>

| Method | Endpoint |
|---|---|
| `search(q, …)` | `GET /companies/search` |
| `search_officers(q, …)` | `GET /companies/search/officers` |
| `advanced_search(…)` | `GET /companies/advanced-search` |
| `get(company_number)` | `GET /companies/{n}` |
| `dossier(n)` | `GET /companies/{n}/dossier` |
| `officers(n)` | `GET /companies/{n}/officers` |
| `pscs(n)` | `GET /companies/{n}/persons-with-significant-control` |
| `psc_statements(n)` | `GET /companies/{n}/persons-with-significant-control-statements` |
| `psc_chain_depth(n)` | `GET /companies/{n}/psc-chain-depth` |
| `psc_chain_tree(n)` | `GET /companies/{n}/psc-chain-tree` |
| `charges(n)` | `GET /companies/{n}/charges` |
| `charge(n, charge_id)` | `GET /companies/{n}/charges/{id}` |
| `insolvency(n)` | `GET /companies/{n}/insolvency` |
| `disqualifications(n)` | `GET /companies/{n}/disqualifications` |
| `officer_disqualification(n, officer_id)` | `GET /companies/{n}/officers/{id}/disqualification` |
| `officer_appointments(officer_id, …)` | `GET /companies/officers/{id}/appointments` |
| `filing_history(n, …)` **Professional** | `GET /companies/{n}/filing-history` |
| `filing_extract(n, transaction_id)` **Professional** | `GET /companies/{n}/filing-history/{tx}/extract` |
| `statement_of_capital(n)` **Professional** | `GET /companies/{n}/statement-of-capital` |

`dossier()` returns profile, officers, PSCs, charges, insolvency and filings in one
request — cheaper than six separate calls.
</details>

<details>
<summary><b>Assessments and rules</b> — <code>client.kyc</code>, <code>client.rule_sets</code>, <code>client.rules</code></summary>

| Method | Endpoint |
|---|---|
| `kyc.assess(company_number \| q, …)` | `GET /kyc/assess` |
| `rule_sets.list()` | `GET /rule-sets` |
| `rules.list()` | `GET /rules` |
| `rules.fields()` | `GET /rules/fields` |
| `jobs.get(job_id)` | `GET /jobs/{id}` |
</details>

<details>
<summary><b>Screening</b> — <code>client.sanctions</code>, <code>client.news</code>, <code>client.offshore_leaks</code></summary>

| Method | Endpoint |
|---|---|
| `sanctions.status()` | `GET /sanctions/status` |
| `sanctions.meta()` | `GET /sanctions/meta` |
| `sanctions.screen(name, …)` | `GET /sanctions/screen` |
| `sanctions.screen_names([…])` | `POST /sanctions/screen-names` |
| `sanctions.entities(…)` | `GET /sanctions/entities` |
| `news.status()` | `GET /news/status` |
| `news.search_names([…])` **Professional** | `POST /news/search-names` |
| `news.search_entities([…])` **Professional** | `POST /news/search-entities` |
| `news.screen_company(n)` **Professional** | `GET /news/screen-company` |
| `offshore_leaks.status()` | `GET /offshore-leaks/status` |
| `offshore_leaks.screen_names([…])` | `POST /offshore-leaks/screen-names` |
| `offshore_leaks.screen_company(n)` | `GET /offshore-leaks/screen-company` |
| `offshore_leaks.node(node_id, …)` | `GET /offshore-leaks/node/{id}` |

Sanctions coverage: OFAC (US), UN Security Council, the UK Sanctions List and the EU
Financial Sanctions Files.
</details>

<details>
<summary><b>Registries</b> — <code>client.fca</code>, <code>client.gleif</code>, <code>client.individual_insolvency</code>, <code>client.charity</code>, <code>client.hmrc_vat</code></summary>

| Method | Endpoint |
|---|---|
| `fca.status()` | `GET /fca/status` |
| `fca.search(q)` | `GET /fca/search` |
| `fca.firm(frn)` | `GET /fca/firm/{frn}` |
| `fca.firm_names(frn)` | `GET /fca/firm/{frn}/names` |
| `fca.firm_individuals(frn)` | `GET /fca/firm/{frn}/individuals` |
| `fca.screen_individuals(n)` | `GET /fca/screen-individuals` |
| `fca.check_individual(name)` | `GET /fca/check-individual` |
| `gleif.company(n)` | `GET /gleif/company` |
| `individual_insolvency.screen_company(n)` | `GET /individual-insolvency/screen-company` |
| `charity.status()` | `GET /charity/status` |
| `charity.search(q)` | `GET /charity/search` |
| `charity.get(regno, …)` | `GET /charity/charity/{regno}` |
| `charity.trustees(regno)` | `GET /charity/charity/{regno}/trustees` |
| `hmrc_vat.status()` | `GET /hmrc-vat/status` |
| `hmrc_vat.check(vat_number)` | `GET /hmrc-vat/check` |
</details>

<details>
<summary><b>Reference data</b> — <code>client.jurisdictions</code>, <code>client.offshore_jurisdictions</code></summary>

| Method | Endpoint |
|---|---|
| `jurisdictions.list()` | `GET /jurisdictions` |
| `jurisdictions.check(country)` | `GET /jurisdictions/check` |
| `offshore_jurisdictions.list()` | `GET /offshore-jurisdictions` |
| `offshore_jurisdictions.check(name)` | `GET /offshore-jurisdictions/check` |

FATF listings are refreshed after each plenary (roughly February, June and October).
</details>

<details>
<summary><b>AI analysis and docs</b> — <code>client.analysis</code>, <code>client.docs</code></summary>

| Method | Endpoint |
|---|---|
| `analysis.status()` | `GET /analysis/status` |
| `analysis.company(n, …)` **Professional** | `POST /analysis/company` |
| `analysis.adverse_media_overview(n, …)` **Professional** | `POST /analysis/adverse-media-overview` |
| `analysis.filing_extract(n, tx, …)` | `POST /analysis/filing-extract` |
| `docs.ask(message, …)` | `POST /docs/ask` |
</details>

<details>
<summary><b>Health</b></summary>

| Method | Endpoint |
|---|---|
| `client.health()` | `GET /health` |
| `client.data_source_health()` | `GET /health/data-sources` |
</details>

Endpoints that proxy an upstream registry return the decoded JSON as a plain `dict`, so
new upstream fields reach you the day they ship instead of waiting on a client release.
The assessment result — the one response shape this API owns — is fully typed.

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
- **Check `is_partial` before recording a clean result.** See
  [Partial results](#partial-results-are-marked-as-partial).
- **Registry data has a lag.** `assessment.data_fetched_at` tells you how fresh the
  underlying Companies House data is.

## Other languages

| Language | Package | Repository |
|---|---|---|
| Python | [`kyccentral`](https://pypi.org/project/kyccentral/) | [kyccentral-python](https://github.com/qualia91/kyccentral-python) |
| JavaScript / TypeScript | [`@kyccentral/sdk`](https://www.npmjs.com/package/@kyccentral/sdk) | [kyccentral-js](https://github.com/qualia91/kyccentral-js) |
| Elixir / Erlang | [`kyccentral`](https://hex.pm/packages/kyccentral) | [kyccentral-elixir](https://github.com/qualia91/kyccentral-elixir) |

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/qualia91/kyccentral-python
cd kyccentral-python
pip install -e ".[dev]"
pytest
```

The test suite mocks every HTTP call, so it runs offline and needs no API key.

## Licence

[MIT](LICENSE) © KYC Central
