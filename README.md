<table>
  <tr>
    <td valign="middle">
      <a href="https://kyccentral.co.uk">
        <img src="assets/site_icon.png" alt="Icon" width="100">
      </a>
    </td>
    <td valign="middle">
      <a href="https://kyccentral.co.uk">
        <h1>
          KYC Central<br>
          Official API clients
        </h1>
      </a>
    </td>
  </tr>
</table>

Open-source client libraries for the [KYC Central](https://kyccentral.co.uk) API, one per
language. Each directory is a **self-contained repository root** — its own README,
licence, changelog, CI, issue templates and release workflow — so it can be split out to
a public repository without rearranging anything.

| Language | Directory | Package |
|---|---|---|
| Python | [`python/`](python) | [`kyccentral`](https://pypi.org/project/kyccentral/) |
| JavaScript / TypeScript | [`javascript/`](javascript) | [`@kyccentral/sdk`](https://www.npmjs.com/package/@kyccentral/sdk) |
| Elixir / Erlang | [`elixir/`](elixir) | [`kyccentral`](https://hex.pm/packages/kyccentral) |

<!-- badges:start -->
## Badges

| Status | Badge |
|---|---|
| CI | [![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-python.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-python.yml) · [![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-javascript.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-javascript.yml) · [![CI](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-elixir.yml/badge.svg)](https://github.com/qualia91/kyc-central-client/actions/workflows/ci-elixir.yml) |
| Code Coverage | [![Codecov](https://codecov.io/gh/qualia91/kyc-central-client/branch/main/graph/badge.svg)](https://codecov.io/gh/qualia91/kyc-central-client) |
| Package Versions | [![PyPI](https://img.shields.io/pypi/v/kyccentral.svg)](https://pypi.org/project/kyccentral/) · [![npm](https://img.shields.io/npm/v/@kyccentral/sdk.svg)](https://www.npmjs.com/package/@kyccentral/sdk) · [![Hex.pm](https://img.shields.io/hexpm/v/kyccentral.svg)](https://hex.pm/packages/kyccentral) |
| Supported Platforms | [![Python](https://img.shields.io/pypi/pyversions/kyccentral.svg)](https://pypi.org/project/kyccentral/) · [![Node](https://img.shields.io/badge/node.js-%3E%3D20-339933.svg?logo=node.js&logoColor=white)](https://www.npmjs.com/package/@kyccentral/sdk) · [![Elixir](https://img.shields.io/badge/elixir-%3E%3D1.15-4B275F.svg?logo=elixir&logoColor=white)](https://hex.pm/packages/kyccentral) |
| Code Quality | [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff-badge/main/badge.json)](https://astral.sh/ruff) · [![ESLint](https://img.shields.io/badge/ESLint-F7DF1E.svg?logo=eslint&logoColor=black)](https://eslint.org/) · [![Credo](https://img.shields.io/badge/Credo-009241.svg?logo=elixir&logoColor=white)](https://github.com/rrrene/credo) · [![TypeScript](https://badgen.net/typescript/definition/@kyccentral/sdk)](https://www.npmjs.com/package/@kyccentral/sdk) |
| Community | [![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg?style=flat-square)](https://github.com/qualia91/kyc-central-client/pulls) · [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT) · [![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](https://www.contributor-covenant.org/version/2/1/0/) · [![Security Policy](https://img.shields.io/badge/security%20policy-enabled-brightgreen.svg)](https://github.com/qualia91/kyc-central-client/blob/main/SECURITY.md) |
<!-- badges:end -->

## Why they live here

All three clients are generated from the same live OpenAPI schema, so a single API
contract change means updating three codebases. Keeping them in one repository makes
that an atomic commit rather than three separate PRs.

The backend API itself lives in a separate private repository, so client↔backend
changes still span two repos — this monorepo at least keeps client↔client changes
atomic. Each directory is a **self-contained package root** (its own README, licence,
changelog, CI and release workflow), so it can be split out to a public repository
later without rearranging anything. Splitting a directory out later preserves its
history:

```bash
git subtree split --prefix=python -b kyccentral-python
```

## Shared design

All three clients were built from the same live OpenAPI schema and deliberately behave
the same way, so a team using more than one does not have to learn three sets of rules.

**Coverage.** Every documented `/v1` endpoint, in every client.

**Only the assessment is typed.** `/v1/kyc/assess` is the one response whose shape this
API owns, so it gets a real type — `Assessment` dataclass, TypeScript interface, Elixir
struct — with severity helpers and an `is_partial` / `isPartial` / `partial?` check.
Endpoints that proxy an upstream registry (Companies House, the FCA Register, GLEIF)
return decoded JSON as-is, so new upstream fields reach callers without waiting on a
client release. The untouched payload is always kept on `raw`.

**Queued assessments are hidden.** A cold assessment can exceed a sensible HTTP timeout,
so the API may answer `202 Accepted` with a job id. Every client polls `/v1/jobs/{id}` to
completion and hands back a finished assessment, with an opt-out for callers who want to
drive the polling themselves.

**Identical retry policy.** `GET`s retry timeouts, connection failures and 408/429/5xx
with exponential backoff plus jitter, honouring a `Retry-After` of up to 8 seconds; a
longer one is returned to the caller as a rate-limit error rather than retried early.
`POST`s — the AI endpoints and batch screening — are retried only when the connection was
never established, or on 429/503 with `Retry-After`, so a slow LLM call is never sent (and
billed) twice. The AI endpoints wait 120 seconds by default, overridable per call. Client
errors — 401, 403, 404, 422 — are never retried.

**Anonymous use works.** Reference and lookup endpoints run without a key at a lower rate
limit, so the libraries can be tried before signing up. Assessments and the AI endpoints
require one.

**Minimal dependencies.** Python depends on `httpx`; JavaScript on nothing at all
(platform `fetch`); Elixir on `jason` alone (OTP's `:httpc`). Each exposes a hook for
supplying your own HTTP client.

**Tests are offline.** Every suite mocks or injects the transport, so contributors need
neither network access nor an API key: 92 tests in Python, 101 in JavaScript, 113 in
Elixir.

**Compliance framing is consistent.** Each README states plainly that sanctions and
adverse-media matching is approximate, that unconfirmed matches stay low-severity until
an analyst confirms them, that there is no PEP screening, and that a partial result is
not a clean one.

## Working on a client

Each directory is independent; see its own `CONTRIBUTING.md`.

```bash
cd python     && pip install -e ".[dev]" && pytest
cd javascript && npm install             && npm test
cd elixir     && mix deps.get            && mix test
```

## Keeping them in step with the API

These clients are generated from, and checked against, the live schema at
`GET /openapi.json` (served by the backend API, which lives in a separate private
repository). When a public endpoint is added, changed or removed in the backend:

1. Update the resource module in all three clients, plus their endpoint tables.
2. Add a routing test in each suite — they all have a table-driven test that asserts each
   function hits the URL the API documents.
3. Add a `## Unreleased` entry to each `CHANGELOG.md`.

Endpoints registered with `include_in_schema=False` are internal (billing, workspaces,
PDF, admin, investigator) and are deliberately **not** covered.