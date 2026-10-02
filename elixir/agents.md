# Agents.md — Elixir / Erlang client (`kyccentral` on Hex)

Language-specific context for this package. The shared design every client follows
(retry policy, queued-assessment polling, "only the assessment is typed", offline
tests) lives in the monorepo's root `agents.md`. When working inside the monorepo,
read that first.

## Layout

- `lib/kyccentral.ex` — `KYCCentral.new/1` builds a plain config struct (no
  processes, nothing to supervise); `health/1`, `data_source_health/1`.
- `lib/kyccentral/transport.ex` — everything HTTP: URL/query building, retry loop,
  decoding, the default `:httpc` transport (`httpc_http/1`, with TLS peer
  verification), `segment/2` and `names_body/2`.
- `lib/kyccentral/{companies,kyc,screening,registries,analysis}.ex` — resource
  modules. Several files define more than one module (e.g. `kyc.ex` holds `Jobs`,
  `RuleSets`, `Rules` and `KYC`).
- `lib/kyccentral/assessment.ex` — `Assessment`, `RiskFlag`, `RuleResult` structs.
  Severities and statuses map through explicit lookup tables, never
  `String.to_atom`/`to_existing_atom`.
- `lib/kyccentral/error.ex` — the single `%KYCCentral.Error{kind: ...}` exception.
- `test/support/stub.ex` — `KYCCentral.Stub`: an injected `:http` function that
  records calls. Every test uses it. Base URL `https://api.test.invalid`.

## Commands

```bash
mix deps.get
mix test
mix format --check-formatted
mix credo --strict
mix dialyzer
mix coveralls          # CI enforces --fail-under 80
```

`mix`/`elixir` may not be installed on every dev machine. If they're missing, say
the Elixir changes weren't verified locally. Don't claim they pass; CI
(`.github/workflows/ci-elixir.yml`) will run them.

## Rules specific to this package

- **Every public function returns `{:ok, result}` or `{:error, %KYCCentral.Error{}}`.**
  Caller mistakes return `kind: :invalid_argument` rather than raising. The only
  raises are in `KYCCentral.new/1` for invalid config.
- Public functions take the client struct first, then required args, then a keyword
  `opts`. Add `@doc` and `@spec` for every public function (Dialyzer runs in CI).
- Path parameters always go through `segment/2` inside a `with`.
- Runtime dependency is `jason` only; the default transport is OTP `:httpc`. Don't
  add an HTTP client dependency.
- `elixir: "~> 1.15"`; CI covers 1.15–1.20 on OTP 26–29. `:public_key.cacerts_get/0`
  needs OTP 25+.
