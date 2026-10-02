# Contributing

Thanks for helping improve the KYC Central Python client. Bug reports, documentation
fixes and new endpoint coverage are all welcome.

## Getting set up

```bash
git clone https://github.com/qualia91/kyccentral-python
cd kyccentral-python
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest                      # test suite — fully mocked, no network, no API key
ruff check .                # lint
ruff format --check .       # formatting
mypy                        # type checking
```

Every one of these runs in CI on Python 3.10 through 3.13. Please make sure they pass
locally before opening a pull request.

## House rules

**Tests never touch the network.** The suite mocks HTTP with
[`respx`](https://lundberg.github.io/respx/), so it runs offline and contributors don't
need an API key. Please don't add tests that call the live API.

**Never commit credentials.** No API keys in tests, fixtures, examples or commit
messages. Use obviously fake values like `"test-key"`.

**Real payloads, redacted.** When adding a fixture for a new endpoint, base it on a real
response but replace personal data — names, addresses, dates of birth — with invented
values. This library screens people; its test data shouldn't contain any.

**Keep the sync and async clients in step.** Every resource module defines both a
blocking class and an `Async`-prefixed twin with identical method names, signatures and
behaviour. A method added to one must be added to the other, and both need a test.

**Match the API, don't reinterpret it.** Endpoints that proxy an upstream registry
return decoded JSON as a plain `dict` on purpose, so new upstream fields reach callers
without waiting on a release here. Only the assessment result is modelled as a typed
class, because it is the one shape this API owns.

## Adding an endpoint

1. Add the method to the sync class in the right `src/kyccentral/resources/` module, and
   the matching method to its `Async` twin.
2. Write a docstring that says what the endpoint returns and flags any plan requirement.
3. Add a routing test to `tests/test_resources.py`, plus a behaviour test if the method
   validates arguments or transforms a body.
4. Add a row to the endpoint table in `README.md`.
5. Add a line to `CHANGELOG.md` under `## Unreleased`.

## Reporting a bug

Open an issue with the client version, Python version, the call you made and the full
traceback. **Redact your API key and any real company or personal data first.**

Security issues go to <security@kyccentral.co.uk> instead — see [SECURITY.md](SECURITY.md).

## Releasing

Maintainers only: releases are cut from the monorepo with `release.py`, which versions
all three clients together (see `PUBLISHING.md` at the repository root).
