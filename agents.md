# Agents.md — KYC Central API clients

This file gives agents working in this repository the context they need: what the
codebase is, how it is organised, the invariants that must be preserved when editing
it, and where to find detailed instructions for each part.

## What this repository is

A monorepo of **official open-source client libraries** for the
[KYC Central](https://kyccentral.co.uk) API — UK company KYC and AML risk assessment.
One client per language:

| Language | Directory | Package | Public repo (mirror) |
|---|---|---|---|
| Python | `python/` | `kyccentral` (PyPI) | kyccentral-python |
| JavaScript / TypeScript | `javascript/` | `@kyccentral/sdk` (npm) | kyccentral-js |
| Elixir / Erlang | `elixir/` | `kyccentral` (Hex) | kyccentral-elixir |

All three clients are generated from the **same live OpenAPI schema**
(`GET /openapi.json`, served by the backend, which lives in a separate private
repository). A schema change means coordinated changes across all three languages, and
this monorepo exists so those client↔client changes are a single atomic commit.

## Repository layout

Each language directory is a **self-contained repository root**: its own `README.md`,
`LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
CI config and examples — so it can be split out (`git subtree split`) to a public
repository without rearranging anything. Work inside one of these directories exactly
as you would in a standalone repo, and keep per-package changes confined to that
directory.

- `python/` — client package in `src/kyccentral/`; resource modules in
  `src/kyccentral/resources/`; tests in `tests/` (mocked with `respx`, offline).
- `javascript/` — client in `src/`, built with `tsup` to `dist/` (ESM + CJS + .d.ts);
  tests in `test/` (vitest); type-checked with `tsc`.
- `elixir/` — client modules in `lib/`; tests in `test/` (ExUnit); type-checked
  with Dialyzer, linted with Credo.
- `.github/workflows/` — CI (one workflow per language) and `publish.yml`.
- Root files: `README.md` (overview), `PUBLISHING.md` (release process), `release.py`,
  `agents.md` (this file).

`CLAUDE.md`, `GEMINI.md` and `.clinerules/cline.md` are stubs that point here. Each
language directory also has its own `agents.md` (layout, commands, language-specific
rules) with a `CLAUDE.md` stub beside it. They travel with the package when it is
split out to its public mirror.

## Shared design (preserve in every edit)

Every client deliberately behaves like the others, so a team using more than one does
not have to learn three sets of rules. When you change one client, mirror the change
in the other two.

- **Full `/v1` coverage.** Every documented public `/v1` endpoint, in every client.
  Endpoints registered with `include_in_schema=False` in the backend (billing,
  workspaces, PDF, admin, investigator) are internal and deliberately **not** covered.
- **Only the assessment is typed.** `v1/kyc/assess` is the one response shape the API
  owns → `Assessment` dataclass / TypeScript interface / Elixir struct, with severity
  helpers and an `is_partial` / `isPartial` / `partial?` check. Endpoints that proxy an
  upstream registry (Companies House, FCA Register, GLEIF, …) return decoded JSON
  as-is so new upstream fields reach callers without a client release. The untouched
  payload is kept on `raw`.
- **Queued assessments are hidden.** A cold assessment can exceed an HTTP timeout, so
  the API may answer `202 Accepted` with a job id. Every client polls `/v1/jobs/{id}`
  to completion and hands back a finished assessment, with an opt-out for callers who
  want to drive polling themselves.
- **Identical retry policy.** Timeouts, connection failures and 408/429/5xx retried
  with exponential backoff + jitter, honouring `Retry-After`; 401, 403, 404, 422 are
  never retried.
- **Anonymous use works.** Reference and lookup endpoints run without a key at a lower
  rate limit; assessments and the AI endpoints require one.
- **Minimal dependencies.** Python: `httpx`; JavaScript: nothing (platform `fetch`);
  Elixir: `jason` alone (OTP's `:httpc`). Each exposes a hook for a custom HTTP client.
- **Tests are offline.** Every suite mocks or injects the transport — no network, no
  API key needed to run the tests.
- **Compliance framing is consistent.** Sanctions/adverse-media matching is
  approximate; unconfirmed matches stay low-severity until an analyst confirms them;
  there is no PEP screening; a partial result is not a clean one.

## Tooling & commands

```bash
# Python
cd python && pip install -e ".[dev]"
pytest                      # offline suite, mock HTTP via respx
ruff check .                # lint
ruff format --check .       # format check
mypy                        # strict type checking

# JavaScript
cd javascript && npm install
npm test                    # vitest, offline
npm run typecheck           # tsc --noEmit
npm run lint                # eslint
npm run format:check        # prettier
npm run build               # tsup → dist/

# Elixir
cd elixir && mix deps.get
mix test                    # ExUnit, offline
mix credo                   # lint
mix dialyzer                # type checking
mix format --check-formatted
mix coveralls               # coverage
```

## Contribution rules

Per-language details live in each `CONTRIBUTING.md`; the house rules all three share:

- **Tests never touch the network** and contributors don't need an API key.
- **Never commit credentials.** Fake values like `"test-key"` in tests/fixtures/
  examples.
- **Real payloads, redacted.** Fixtures for a new endpoint are based on real responses
  with personal data (names, addresses, DOB) replaced by invented values. This library
  screens people; its test data must not contain any.
- **Keep parallel clients in step.** Python has sync + `Async`-prefixed twins with
  identical methods; the three languages mirror each other. A method added to one must
  be added to its twins, each with a test.
- **Match the API, don't reinterpret it.** Typed models only where the API owns the
  shape; proxied upstream payloads stay plain dicts/JSON.

### Adding/changing an endpoint

When a public endpoint is added, changed or removed in the backend:

1. Update the resource module(s) in **all three clients** (plus their endpoint tables
   and READMEs).
2. Add a routing test in each suite — each language has a table-driven test asserting
   each function hits the URL the API documents.
3. Add a `## Unreleased` entry to each changed client's `CHANGELOG.md`.
4. If it's a user-visible behaviour change, keep the shared design above intact.

## CI & publishing

- CI: `.github/workflows/ci-{python,javascript,elixir}.yml` — run the full
  test + lint + format + type-check suite per language.
- Publishing: a single `vX.Y.Z` git tag on `main` triggers `publish.yml`, which runs
  the full suite for each client whose directory changed since the previous `v*` tag,
  then publishes to PyPI (trusted publishing), npm (`--provenance`) or Hex
  (`HEX_API_KEY`). Full process in `PUBLISHING.md`.
- **Version bump discipline:** bump only the version of the clients that changed
  (`python/src/kyccentral/_version.py`, `javascript/package.json`, `elixir/mix.exs`),
  move `## Unreleased` entries under a new `## X.Y.Z — YYYY-MM-DD` heading, commit
  `Release vX.Y.Z`, then tag and push.

## Where to look next

- `python/agents.md`, `javascript/agents.md`, `elixir/agents.md` — per-package
  layout, commands and rules for agents.
- Root `README.md` — overview and the shared design in full.
- `python/CONTRIBUTING.md`, `javascript/CONTRIBUTING.md`, `elixir/CONTRIBUTING.md` —
  per-language setup, house rules and release steps.
- `PUBLISHING.md` — one-time trusted-publisher setup and the per-release steps.
- Each client's `README.md` — endpoint tables, usage and compliance framing.