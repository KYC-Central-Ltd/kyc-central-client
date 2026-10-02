# Contributing

Thanks for helping improve the KYC Central JavaScript client. Bug reports, documentation
fixes and new endpoint coverage are all welcome.

## Getting set up

```bash
git clone https://github.com/qualia91/kyccentral-js
cd kyccentral-js
npm install
```

## Running the checks

```bash
npm test            # test suite — fetch is mocked, no network, no API key
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run format:check
npm run build       # tsup: ESM + CJS + type declarations
```

All of these run in CI on Node 22 and 24. Please make sure they pass locally before
opening a pull request.

## House rules

**No runtime dependencies.** This package deliberately ships with an empty `dependencies`
block — it uses the platform `fetch`. A pull request that adds one needs a very good
reason, because it lands in every consumer's dependency tree.

**Tests never touch the network.** The suite injects a mock `fetch`, so it runs offline
and contributors don't need an API key. Please don't add tests that call the live API.

**Never commit credentials.** No API keys in tests, fixtures, examples or commit
messages. Use obviously fake values like `'test-key'`.

**Real payloads, redacted.** When adding a fixture for a new endpoint, base it on a real
response but replace personal data — names, addresses, dates of birth — with invented
values. This library screens people; its test data shouldn't contain any.

**Failures reject, they don't throw.** Every public method is `async`, including ones
whose only work before the request is argument validation. That keeps a single
`.catch()` sufficient for callers; a method that throws synchronously would slip past it.

**Match the API, don't reinterpret it.** Endpoints that proxy an upstream registry are
typed as `JsonObject` on purpose, so new upstream fields reach callers without waiting on
a release here. Only the assessment result is fully typed, because it is the one shape
this API owns.

**Runtime portability matters.** The package targets Node, Deno, Bun, workers and the
browser. Don't reach for Node built-ins; guard anything that touches `process`.

## Adding an endpoint

1. Add the method to the right class in `src/resources/`, as an `async` method.
2. Write a TSDoc comment that says what the endpoint returns and flags any plan
   requirement.
3. Export any new option interface from `src/index.ts`.
4. Add a routing case to `test/resources.test.ts`, plus a behaviour test if the method
   validates arguments or transforms a body.
5. Add a row to the endpoint table in `README.md`.
6. Add a line to `CHANGELOG.md` under `## Unreleased`.

## Reporting a bug

Open an issue with the client version, your runtime and version, the call you made and
the full error. **Redact your API key and any real company or personal data first.**

Security issues go to <security@kyccentral.co.uk> instead — see [SECURITY.md](SECURITY.md).

## Releasing

Maintainers only: releases are cut from the monorepo with `release.py`, which versions
all three clients together (see `PUBLISHING.md` at the repository root).
