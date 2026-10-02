# Agents.md — Python client (`kyccentral` on PyPI)

Language-specific context for this package. The shared design every client follows
(retry policy, queued-assessment polling, "only the assessment is typed", offline
tests) lives in the monorepo's root `agents.md`. When working inside the monorepo,
read that first.

## Layout

- `src/kyccentral/client.py` — `KYCCentral` (sync) and `AsyncKYCCentral` (async)
  entry points. They wire one resource object per namespace onto the client.
- `src/kyccentral/_transport.py` — everything HTTP: config resolution, headers,
  retry loop (`SyncTransport` / `AsyncTransport`), `_seg()` path-segment
  validation, `_names_body()` for batch endpoints. Internal, not public API.
- `src/kyccentral/resources/*.py` — one module per area (`companies`, `kyc`,
  `screening`, `registries`, `analysis`). Every class has an `Async`-prefixed twin
  in the same module.
- `src/kyccentral/models.py` — `Assessment`, `RiskFlag`, `RuleResult`, `RiskLevel`,
  `RuleStatus`. The only typed response.
- `src/kyccentral/errors.py` — exception hierarchy rooted at `KYCCentralError`;
  `status_error_from_response()` maps HTTP status to class.
- `src/kyccentral/_version.py` — the single source of the package version.
- `tests/` — pytest + `respx`; fixtures in `tests/conftest.py`
  (`client`, `async_client`, `assessment_payload`). Base URL `https://api.test.invalid`.

## Commands

```bash
pip install -e ".[dev]"     # prefer a virtualenv
pytest                      # offline; addopts also writes coverage.xml (fail-under 80%)
ruff check .
ruff format --check .
mypy                        # strict
```

## Rules specific to this package

- **Sync/async twins move together.** A method added to `Companies` must be added to
  `AsyncCompanies` with an identical signature and docstring summary, plus a test for
  each. Put shared request-building logic in a module-level helper (see
  `_assess_params`, `_company_body`) so the twins cannot drift.
- Path parameters always go through `_seg(value, "name")`; never interpolate raw input.
- Optional query params are passed as `None` and dropped by `_clean_params`. Don't
  pre-filter them in the resource.
- Proxied upstream payloads are returned as plain `dict`/`list`. Don't add dataclasses
  for them.
- Python 3.10 is the floor (`requires-python = ">=3.10"`). Use `from __future__ import
  annotations`; no 3.11+ only syntax.
- Runtime dependency is `httpx` only. Don't add another.
