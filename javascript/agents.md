# Agents.md — JavaScript / TypeScript client (`@kyccentral/sdk` on npm)

Language-specific context for this package. The shared design every client follows
(retry policy, queued-assessment polling, "only the assessment is typed", offline
tests) lives in the monorepo's root `agents.md`. When working inside the monorepo,
read that first.

## Layout

- `src/client.ts` — `KYCCentral`, which wires one resource object per namespace.
- `src/transport.ts` — everything HTTP: options resolution, `buildQuery`, retry loop,
  timeout/abort signal combination, `seg()` path-segment validation, `namesBody()`.
  Internal, not public API.
- `src/resources/*.ts` — one module per area (`companies`, `kyc`, `screening`,
  `registries`, `analysis`).
- `src/types.ts` — `Assessment` interface plus free-function helpers (`isPartial`,
  `flagsAtOrAbove`, …). Helpers are free functions on purpose, so an `Assessment`
  stays a plain object that survives `structuredClone`/JSON/React state.
- `src/errors.ts` — error classes rooted at `KYCCentralError`;
  `statusErrorFromResponse()` maps HTTP status to class.
- `src/index.ts` — the public export list. Anything new and public must be exported
  here.
- `test/` — vitest with a mocked `fetch` (`test/helpers.ts`: `mockFetch`,
  `jsonResponse`, `assessmentPayload`). Base URL `https://api.test.invalid`.

## Commands

```bash
npm ci
npm test               # vitest run, offline
npm run typecheck      # tsc --noEmit
npm run lint           # eslint
npm run format:check   # prettier (npm run format to fix)
npm run build          # tsup → dist/ (ESM + CJS + .d.ts)
```

## Rules specific to this package

- **Zero runtime dependencies.** Platform `fetch` only. The package must keep working
  on Node ≥ 22 (see `engines`), Deno, Bun, Workers and browsers. Guard any use of
  `process`, and feature-detect newer APIs.
- Imports use explicit `.js` extensions (ESM output).
- Method names are camelCase mirrors of the Python/Elixir snake_case names; option
  objects use camelCase keys mapped to the API's snake_case query/body fields inside
  the resource.
- Every resource method accepts a trailing options object extending `CallOptions`
  (for `signal`) and forwards `signal` to the transport.
- Path parameters always go through `seg(value, 'name')`.
- Proxied upstream payloads are typed `JsonObject`. Don't add interfaces for them.
