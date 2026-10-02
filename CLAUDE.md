# Agent Context

This repository's agent context lives in [agents.md](agents.md), shared with other
coding agents. It's imported here so it is always loaded:

@agents.md

## Claude Code notes

- **Context is layered.** `python/`, `javascript/` and `elixir/` each have their own
  `agents.md` (imported by a `CLAUDE.md` stub there), which loads when you work in
  that directory. Put language-specific guidance there and cross-client guidance in the
  root `agents.md`. Edit `agents.md`, not the `CLAUDE.md` stubs, so other agents see
  the same context.
- **A behaviour change is three changes.** Before calling a client change done, check
  the same change exists in the other two clients (and in the Python `Async` twin),
  each with a test and an `## Unreleased` CHANGELOG entry.
- **Verify per language you touched.** Run that package's full command set from its
  `agents.md`, not only the tests. If a toolchain is missing locally (commonly
  `mix`), report the package as unverified instead of guessing.
- **Keep the tree clean.** Use a virtualenv outside the repo or the session scratchpad.
  `pytest` writes `python/coverage.xml`, so delete it before finishing.
- **Never release on your own.** Don't run `release.py`, create or push `v*` tags, or
  edit `.github/workflows/publish.yml` without explicit instruction: a `v*` tag
  publishes to PyPI, npm and Hex.
- **Compliance wording is deliberate.** Docstrings and READMEs carefully say that
  matches are approximate, unconfirmed hits are low severity, there is no PEP
  screening, and a partial result is not a clean one. Preserve that framing when
  editing.
- Project skills live in `.claude/skills/`.
