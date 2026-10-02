<div align="center">

# KYC Central — Elixir client

**UK company KYC and AML risk assessment, from one API call.**

[![Hex.pm](https://img.shields.io/hexpm/v/kyccentral.svg)](https://hex.pm/packages/kyccentral)
[![Docs](https://img.shields.io/badge/hex-docs-blue.svg)](https://hexdocs.pm/kyccentral)
[![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-elixir.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-elixir.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[Website](https://kyccentral.co.uk) · [API reference](https://kyccentral.co.uk/api-docs) · [Get an API key](https://kyccentral.co.uk/account) · [Other clients](#other-languages)

</div>

---

Screen a UK company against Companies House, the FCA Register, GLEIF, the Insolvency
Service, OFAC / UN / UK / EU sanctions lists, adverse media and the ICIJ Offshore Leaks
database — then run a configurable rule engine over the result and get back a structured
list of risk flags.

```elixir
client = KYCCentral.new()                       # reads KYCCENTRAL_API_KEY
{:ok, assessment} = KYCCentral.KYC.assess(client, "00445790")

IO.puts("#{assessment.company_name} → #{assessment.risk_level}")

for flag <- KYCCentral.Assessment.flags_at_or_above(assessment, :high) do
  IO.puts("  [#{flag.severity}] #{flag.code}: #{flag.description}")
end
```

```
TESCO PLC → medium
  [high] ACCOUNTS_OVERDUE: Annual accounts are 42 days overdue.
```

**One runtime dependency.** The default transport is OTP's own `:httpc`, so adding this
client pulls in [Jason](https://hex.pm/packages/jason) and nothing else — no HTTP stack,
no supervision tree, nothing to start. Prefer Req, Finch or Tesla? [Plug yours in](#using-a-different-http-client).

## Contents

- [Install](#install)
- [Authentication](#authentication)
- [Quick start](#quick-start)
- [Working with an assessment](#working-with-an-assessment)
- [Error handling](#error-handling)
- [Retries, timeouts and TLS](#retries-timeouts-and-tls)
- [Using a different HTTP client](#using-a-different-http-client)
- [Calling from Erlang](#calling-from-erlang)
- [Rate limits and plans](#rate-limits-and-plans)
- [API coverage](#api-coverage)
- [Compliance notes](#compliance-notes)
- [Contributing](#contributing)

## Install

Add `:kyccentral` to your dependencies in `mix.exs`:

```elixir
def deps do
  [
    {:kyccentral, "~> 0.1"}
  ]
end
```

Requires Elixir 1.15+ and OTP 25+.

## Authentication

Generate a key in [Account settings](https://kyccentral.co.uk/account), then either set
an environment variable:

```bash
export KYCCENTRAL_API_KEY="your_key"
```

```elixir
client = KYCCentral.new()
```

…or pass it explicitly:

```elixir
client = KYCCentral.new(api_key: "your_key")
```

**A key is not always required.** Reference and lookup endpoints — company search,
sanctions screening, FATF jurisdictions, health — work anonymously at a lower rate limit,
which makes the library easy to try before you sign up. Assessments
(`KYCCentral.KYC.assess/3`) and the AI endpoints always need a key.

`KYCCentral.new/1` returns a plain struct. It starts no processes and opens no
connections, so there is nothing to supervise and nothing to close — build one and pass
it around, or memoise it in your application's state.

## Quick start

```elixir
alias KYCCentral.Assessment

client = KYCCentral.new()

with {:ok, %{"items" => [%{"company_number" => number} | _]}} <-
       KYCCentral.Companies.search(client, "tesco plc", items_per_page: 5),
     {:ok, assessment} <- KYCCentral.KYC.assess(client, number) do
  cond do
    Assessment.flags_at(assessment, [:critical]) != [] ->
      {:block, Assessment.flags_at(assessment, [:critical])}

    assessment.risk_level == :low and not Assessment.partial?(assessment) ->
      :clear

    true ->
      :refer
  end
end
```

## Working with an assessment

`assess/3` returns a `%KYCCentral.Assessment{}`:

```elixir
assessment.company_name      # "TESCO PLC"
assessment.risk_level        # :medium
assessment.flags             # [%KYCCentral.RiskFlag{code: "ACCOUNTS_OVERDUE", ...}]
assessment.rule_results      # every rule, including the ones that passed
assessment.checked_at        # when this assessment ran
assessment.data_fetched_at   # how fresh the underlying registry data is
```

Severities and statuses are atoms — `:low`, `:medium`, `:high`, `:critical`,
`:unknown` and `:passed`, `:failed`, `:not_evaluated` — so they pattern-match
cleanly. `:unknown` is a severity or risk level this client version does not
recognise; it ranks above `:critical`, so `flags_at_or_above/2` never filters it
out, and the original string is on `:raw`:

```elixir
case assessment.risk_level do
  level when level in [:critical, :unknown] -> escalate(assessment)
  level when level in [:high, :medium] -> refer(assessment)
  :low -> approve(assessment)
end
```

Helper functions keep the common checks short:

```elixir
alias KYCCentral.Assessment

Assessment.clear?(assessment)                          # no flags at all
Assessment.flags_at(assessment, [:critical])           # blockers
Assessment.flags_at_or_above(assessment, :high)        # by severity
Assessment.has_flag?(assessment, "ACCOUNTS_OVERDUE")   # by code
Assessment.flag(assessment, "PSC_CHAIN_TOO_DEEP")      # -> RiskFlag.t() | nil
Assessment.rules_with_status(assessment, :failed)
```

The evidence each rule was judged against is on the `*_summary` fields —
`:officers_summary`, `:psc_summary`, `:sanctions_summary`, `:charges_summary` and so on
— and the untouched response body is always on `assessment.raw`, so a field this client
version doesn't model yet is never lost.

### Partial results are marked as partial

An assessment fans out to a dozen upstream sources. When one is slow or down, the API
returns what it has and says so rather than silently reporting a clean result:

```elixir
if Assessment.partial?(assessment) do
  Logger.warning("Incomplete assessment",
    timed_out: assessment.timed_out_services,
    failed_rules: assessment.failed_rules
  )
end
```

**Treat `partial?/1` as "not yet screened", not "clean".** An absent flag from a source
that timed out is not evidence of absence.

### Confirming noisy matches

Adverse media and Offshore Leaks matching is fuzzy, so unconfirmed hits only ever raise
a low-severity `*_UNCONFIRMED` flag. Once an analyst has confirmed a specific article or
match, pass it back to promote it to full severity:

```elixir
KYCCentral.KYC.assess(client, "00445790",
  confirmed_media_urls: ["https://news.example/article"],
  confirmed_leak_ids: ["icij-node-12345"]
)
```

### Queued assessments are handled for you

A cold assessment can take longer than a sensible HTTP timeout, so the API may answer
`202 Accepted` with a job id instead of holding the connection open. This client polls
the job and returns the finished assessment either way:

```elixir
KYCCentral.KYC.assess(client, "00445790")                       # blocks until done
KYCCentral.KYC.assess(client, "00445790", poll_timeout: 300_000) # allow longer
KYCCentral.KYC.assess(client, "00445790", wait: false)           # %{"job_id" => ...}
```

## Error handling

Every function returns `{:ok, result}` or `{:error, %KYCCentral.Error{}}`. Errors carry a
`:kind` atom rather than being split across a tree of exception modules, which makes them
pleasant to match on:

```elixir
case KYCCentral.KYC.assess(client, "00445790") do
  {:ok, assessment} ->
    assessment

  {:error, %KYCCentral.Error{kind: :not_found}} ->
    :no_such_company

  {:error, %KYCCentral.Error{kind: :permission_denied, detail: detail}} ->
    {:upgrade_required, detail}

  {:error, %KYCCentral.Error{kind: :rate_limit, retry_after: seconds}} ->
    {:retry_in, seconds}

  {:error, error} ->
    raise error
end
```

| `:kind` | Status | Usual cause |
|---|---|---|
| `:bad_request` | 400 | Malformed request |
| `:authentication` | 401 | Missing or invalid API key |
| `:permission_denied` | 403 | Endpoint needs an active Professional subscription |
| `:not_found` | 404 | No such company, officer, charge, rule or rule set |
| `:unprocessable_entity` | 422 | Failed the API's validation — see `:body` |
| `:rate_limit` | 429 | Rate limit or monthly free quota — see `:retry_after` |
| `:server_error` / `:service_unavailable` | 5xx | API or an upstream dependency failed |
| `:connection` / `:timeout` | — | Never reached the API |
| `:job_failed` / `:job_timeout` | — | A queued assessment failed or outran `:poll_timeout` |
| `:invalid_argument` | — | Caught before any request was made |

`KYCCentral.Error` is an exception, so `raise error` works when you would rather not
handle a failure locally.

## Retries, timeouts and TLS

GETs retry timeouts, connection failures and retryable statuses (408, 429, 500, 502, 503,
504) twice by default, with exponential backoff plus jitter, honouring `Retry-After`.
A `Retry-After` longer than 8 seconds is not waited out; the rate-limit error is returned
straight away with `:retry_after` set, so the caller can schedule the retry.
POSTs are retried only when the connection was never established, or on 429/503 with
`Retry-After`, so a slow AI call is never sent twice. Client errors like 401, 403, 404 and
422 are never retried — they will not become true on a second attempt.

The AI endpoints (`Analysis.company/3`, `Analysis.adverse_media_overview/3`,
`Analysis.filing_extract/4`, `Docs.ask/3`) default to a 120 s timeout, or the client's
`:receive_timeout` if that is longer. Override it per call:

```elixir
KYCCentral.Analysis.company(client, "00445790", receive_timeout: 180_000)
```

```elixir
KYCCentral.new(
  receive_timeout: 60_000,   # per-request, milliseconds
  max_retries: 5             # 0 disables retries entirely
)
```

The default `:httpc` transport verifies TLS properly — `verify_peer` against the OS trust
store, with hostname checking and TLS 1.2/1.3 only. `:httpc` does **not** do this by
default, and a client that carries an API key must never talk to an unverified peer.

## Using a different HTTP client

Pass `:http` — a one-argument function. This is also how the test suite runs offline:

```elixir
# With Req
http = fn request ->
  case Req.request(
         method: request.method,
         url: request.url,
         headers: request.headers,
         body: request.body,
         receive_timeout: request.receive_timeout,
         retry: false,
         redirect: false,
         decode_body: false
       ) do
    {:ok, resp} -> {:ok, %{status: resp.status, headers: resp.headers, body: resp.body}}
    {:error, reason} -> {:error, reason}
  end
end

client = KYCCentral.new(http: http)
```

The function receives `%{method:, url:, headers:, body:, receive_timeout:}` and must
return `{:ok, %{status:, headers:, body:}}` or `{:error, reason}`. Bodies are decoded
centrally, so returning the raw string is correct — this client's retry policy and error
mapping then apply unchanged.

The default transport never follows redirects, so the API key is never sent to another
host; a 3xx surfaces as an `:unexpected_status` error with the `location` header. If you
supply your own `:http` function, make sure it does not follow redirects, or at least does
not forward `X-API-Key` to another origin.

## Calling from Erlang

Elixir modules are reachable from Erlang with an `Elixir.` prefix:

```erlang
Client = 'Elixir.KYCCentral':new([{api_key, <<"your_key">>}]),
{ok, Assessment} = 'Elixir.KYCCentral.KYC':assess(Client, <<"00445790">>),
RiskLevel = maps:get(risk_level, Assessment),
Flags = maps:get(flags, Assessment).
```

Structs are maps with a `'__struct__'` key, so `maps:get/2` reads any field. Add
`{kyccentral, "0.1.0"}` to your `rebar.config` deps.

## Rate limits and plans

| Tier | Limit |
|---|---|
| Anonymous | 30 requests / minute, per IP |
| Authenticated | 120 requests / minute |
| Professional subscription | 60 assessments / minute, full endpoint access |
| Free plan | A fixed number of assessments per calendar month |

Cached results and failed runs don't consume free-plan quota. Endpoints marked
**Professional** below return `{:error, %KYCCentral.Error{kind: :permission_denied}}`
without an active subscription.

Batch endpoints exist precisely to stay inside these limits —
`KYCCentral.Sanctions.screen_names/2` screens up to 500 names in a single request.

## API coverage

Every documented endpoint is available. Each function takes the client as its first
argument.

<details>
<summary><b>Companies</b> — <code>KYCCentral.Companies</code></summary>

| Function | Endpoint |
|---|---|
| `search/3` | `GET /companies/search` |
| `search_officers/3` | `GET /companies/search/officers` |
| `advanced_search/2` | `GET /companies/advanced-search` |
| `get/2` | `GET /companies/{n}` |
| `dossier/2` | `GET /companies/{n}/dossier` |
| `officers/2` | `GET /companies/{n}/officers` |
| `pscs/2` | `GET /companies/{n}/persons-with-significant-control` |
| `psc_statements/2` | `GET /companies/{n}/persons-with-significant-control-statements` |
| `psc_chain_depth/2` | `GET /companies/{n}/psc-chain-depth` |
| `psc_chain_tree/2` | `GET /companies/{n}/psc-chain-tree` |
| `charges/2` | `GET /companies/{n}/charges` |
| `charge/3` | `GET /companies/{n}/charges/{id}` |
| `insolvency/2` | `GET /companies/{n}/insolvency` |
| `disqualifications/2` | `GET /companies/{n}/disqualifications` |
| `officer_disqualification/3` | `GET /companies/{n}/officers/{id}/disqualification` |
| `officer_appointments/3` | `GET /companies/officers/{id}/appointments` |
| `filing_history/3` **Professional** | `GET /companies/{n}/filing-history` |
| `filing_extract/3` **Professional** | `GET /companies/{n}/filing-history/{tx}/extract` |
| `statement_of_capital/2` **Professional** | `GET /companies/{n}/statement-of-capital` |

`dossier/2` returns profile, officers, PSCs, charges, insolvency and filings in one
request — cheaper than six separate calls.
</details>

<details>
<summary><b>Assessments and rules</b></summary>

| Function | Endpoint |
|---|---|
| `KYCCentral.KYC.assess/3` | `GET /kyc/assess` |
| `KYCCentral.RuleSets.list/1` | `GET /rule-sets` |
| `KYCCentral.Rules.list/1` | `GET /rules` |
| `KYCCentral.Rules.fields/1` | `GET /rules/fields` |
| `KYCCentral.Jobs.get/2` | `GET /jobs/{id}` |
</details>

<details>
<summary><b>Screening</b></summary>

| Function | Endpoint |
|---|---|
| `KYCCentral.Sanctions.status/1` | `GET /sanctions/status` |
| `KYCCentral.Sanctions.meta/1` | `GET /sanctions/meta` |
| `KYCCentral.Sanctions.screen/3` | `GET /sanctions/screen` |
| `KYCCentral.Sanctions.screen_names/2` | `POST /sanctions/screen-names` |
| `KYCCentral.Sanctions.entities/2` | `GET /sanctions/entities` |
| `KYCCentral.News.status/1` | `GET /news/status` |
| `KYCCentral.News.search_names/2` **Professional** | `POST /news/search-names` |
| `KYCCentral.News.search_entities/2` **Professional** | `POST /news/search-entities` |
| `KYCCentral.News.screen_company/2` **Professional** | `GET /news/screen-company` |
| `KYCCentral.OffshoreLeaks.status/1` | `GET /offshore-leaks/status` |
| `KYCCentral.OffshoreLeaks.screen_names/2` | `POST /offshore-leaks/screen-names` |
| `KYCCentral.OffshoreLeaks.screen_company/2` | `GET /offshore-leaks/screen-company` |
| `KYCCentral.OffshoreLeaks.node/3` | `GET /offshore-leaks/node/{id}` |

Sanctions coverage: OFAC (US), UN Security Council, the UK Sanctions List and the EU
Financial Sanctions Files.
</details>

<details>
<summary><b>Registries and reference data</b></summary>

| Function | Endpoint |
|---|---|
| `KYCCentral.FCA.status/1` | `GET /fca/status` |
| `KYCCentral.FCA.search/2` | `GET /fca/search` |
| `KYCCentral.FCA.firm/2` | `GET /fca/firm/{frn}` |
| `KYCCentral.FCA.firm_names/2` | `GET /fca/firm/{frn}/names` |
| `KYCCentral.FCA.firm_individuals/2` | `GET /fca/firm/{frn}/individuals` |
| `KYCCentral.FCA.screen_individuals/2` | `GET /fca/screen-individuals` |
| `KYCCentral.FCA.check_individual/2` | `GET /fca/check-individual` |
| `KYCCentral.GLEIF.company/2` | `GET /gleif/company` |
| `KYCCentral.IndividualInsolvency.screen_company/2` | `GET /individual-insolvency/screen-company` |
| `KYCCentral.Charity.status/1` | `GET /charity/status` |
| `KYCCentral.Charity.search/2` | `GET /charity/search` |
| `KYCCentral.Charity.get/3` | `GET /charity/charity/{regno}` |
| `KYCCentral.Charity.trustees/2` | `GET /charity/charity/{regno}/trustees` |
| `KYCCentral.HMRCVat.status/1` | `GET /hmrc-vat/status` |
| `KYCCentral.HMRCVat.check/2` | `GET /hmrc-vat/check` |
| `KYCCentral.Jurisdictions.list/1` | `GET /jurisdictions` |
| `KYCCentral.Jurisdictions.check/2` | `GET /jurisdictions/check` |
| `KYCCentral.OffshoreJurisdictions.list/1` | `GET /offshore-jurisdictions` |
| `KYCCentral.OffshoreJurisdictions.check/2` | `GET /offshore-jurisdictions/check` |

FATF listings are refreshed after each plenary (roughly February, June and October).
</details>

<details>
<summary><b>AI analysis and health</b></summary>

| Function | Endpoint |
|---|---|
| `KYCCentral.Analysis.status/1` | `GET /analysis/status` |
| `KYCCentral.Analysis.company/3` **Professional** | `POST /analysis/company` |
| `KYCCentral.Analysis.adverse_media_overview/3` **Professional** | `POST /analysis/adverse-media-overview` |
| `KYCCentral.Analysis.filing_extract/4` | `POST /analysis/filing-extract` |
| `KYCCentral.Docs.ask/3` | `POST /docs/ask` |
| `KYCCentral.health/1` | `GET /health` |
| `KYCCentral.data_source_health/1` | `GET /health/data-sources` |
</details>

Endpoints that proxy an upstream registry return the decoded JSON as a plain map with
string keys, so new upstream fields reach you the day they ship instead of waiting on a
client release. The assessment result — the one response shape this API owns — is a
typed struct.

## Compliance notes

This library is a client for a data API. It is not, and does not provide, regulatory
advice, and using it does not by itself discharge any obligation under the Money
Laundering Regulations.

- **Sanctions and adverse media matching is approximate.** Sanctions lists carry
  transliterated names, aliases and date-of-birth ranges. Every hit is a candidate for
  human review, not a determination.
- **Unconfirmed matches are deliberately low-severity.** Adverse media and Offshore Leaks
  hits stay at `*_UNCONFIRMED` until an analyst confirms the specific article or match.
  Don't promote them programmatically.
- **There is no PEP screening.** The platform ingests sanctions lists only. Nothing here
  identifies politically exposed persons.
- **Check `Assessment.partial?/1` before recording a clean result.** See
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
git clone https://github.com/qualia91/kyccentral-elixir
cd kyccentral-elixir
mix deps.get
mix test
```

The test suite injects a stub HTTP function, so it runs offline and needs no API key.

## Licence

[MIT](LICENSE) © KYC Central
