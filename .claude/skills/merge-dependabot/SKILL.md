---
name: merge-dependabot
description: Merge every open Dependabot PR into main one at a time via `gh pr merge`, skipping any that aren't safe (merge conflicts or failing checks). Then verify the touched packages with the command sets in their agents.md files, fix or revert anything that breaks, and report what merged, what was skipped and why, and what was fixed. Use when asked to clear the Dependabot backlog, merge dependency bumps, or process open dependabot PRs.
---

# Merging Dependabot PRs into main

`.github/dependabot.yml` targets `main` and groups minor+patch bumps per ecosystem
(`pip-deps` for `python/`, `npm-deps` for `javascript/`, `mix-deps` for `elixir/`,
`github-actions-deps` for workflows). Major bumps are excluded from the groups and
arrive as their own PRs.

Merging to `main` never publishes anything. Only a pushed `v*` tag does. Never run
`release.py`, create or push `v*` tags, or edit `.github/workflows/publish.yml` as
part of this flow.

## 1. Discover

```bash
git fetch origin --prune
gh pr list --search "author:app/dependabot" --base main --state open \
  --json number,title,headRefName,mergeable,mergeStateStatus,url
```

If nothing is open, say so and stop.

## 2. Order the queue

Process **one PR at a time**, re-checking against the current tip of `main` before
each merge (an earlier merge can turn a clean PR into a conflict, for example two PRs
touching the same lockfile). Order:

1. Grouped minor/patch PRs first (`*-deps` groups), lowest PR number first.
2. Standalone major bumps last, since they are the most likely to need more than a
   mechanical merge.

## 3. Per-PR safety check

1. **Conflicts.** `gh pr view <n> --json mergeable,mergeStateStatus`. If `mergeable`
   is `CONFLICTING`, skip (reason: merge conflicts with main). If the PR is only
   behind (`mergeStateStatus` is `BEHIND`), run `gh pr update-branch <n>` and go on to
   the checks, which will re-run.
2. **Checks.** `gh pr checks <n> --watch --interval 30`, giving up after about 10
   minutes. If any required check fails, skip and name the failing check(s). If the
   limit passes with checks still pending, skip with that reason rather than merging
   blind.
3. **Merge** with GitHub, matching the existing "Merge pull request #..." history:
   ```bash
   gh pr merge <n> --merge --delete-branch
   git checkout main && git pull --ff-only
   ```
   Never create merge commits locally and never push to `main` directly.

Keep a running list: merged (PR #, ecosystem/directory, version change) and skipped
(PR #, title, reason).

## 4. Verify

For each package directory touched by a merged PR, run that package's full command
set, exactly as listed in its `agents.md` (read the file; do not work from memory):

- `python/agents.md`: install, `pytest`, `ruff check .`, `ruff format --check .`,
  `mypy`. Use a virtualenv outside the repo (or the session scratchpad), and delete
  `python/coverage.xml` afterwards, since `pytest` writes it.
- `javascript/agents.md`: `npm ci`, `npm test`, `npm run typecheck`, `npm run lint`,
  `npm run format:check`, `npm run build`.
- `elixir/agents.md`: `mix deps.get`, `mix test`, `mix format --check-formatted`,
  `mix credo --strict`, `mix dialyzer`, `mix coveralls`. If `mix` is not installed
  locally, report Elixir as unverified. Do not claim it passes.

A `github-actions` bump touches every language's CI, so run all three sets, and also
`actionlint` if it is installed.

Leave the tree clean (no `dist/`, `node_modules/` or `coverage.xml` left staged or
untracked beyond what is already ignored).

## 5. If verification fails

Fix the root cause on a new branch and open a PR, or revert the offending merge on a
new branch (`git revert -m 1 <merge-sha>`) and open a PR for that. Move the affected
PR to the skipped list with the reason. Never force-push or rewrite `main`.

## 6. Changelog

Dependency bumps get no CHANGELOG entry, unless they change a runtime dependency:
`httpx` for Python or `jason` for Elixir (JavaScript has none). Those get a line under
`## Unreleased` → `### Changed` in that package's `CHANGELOG.md`, added via a PR.

## 7. Report

Finish with a plain-text summary, not a document:

- **Merged**: one line per PR with number, ecosystem/directory, version change, and
  any fix that was needed because of it.
- **Skipped**: one line per PR with number, title, and the concrete reason (which
  check failed, or conflict).
- **Fixes made**: one line each, with the file and root cause (and the PR opened).
- **Final state of `main`**: the head commit, and which packages were verified or
  left unverified.
