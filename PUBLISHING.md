# Publishing

All three clients are published from this monorepo via a single `vX.Y.Z` git tag.
Releases are **lockstep**: every release bumps all three clients to the same version,
whether or not each one changed. The `publish.yml` workflow runs the full test suite
for all three clients, then publishes each to its registry; each job first checks that
its package version equals the tag.

| Language | Package | Registry |
|---|---|---|
| Python | `kyccentral` | [PyPI](https://pypi.org/project/kyccentral/) |
| JavaScript | `@kyccentral/sdk` | [npm](https://www.npmjs.com/package/@kyccentral/sdk) |
| Elixir | `kyccentral` | [Hex](https://hex.pm/packages/kyccentral) |

## One-time setup

These are done once per repository (or once per account if you own all three
registries).

### PyPI (trusted publishing)

PyPI supports [trusted publishing](https://docs.pypi.org/trusted-publishers/) via OIDC,
so you do **not** need to create or store an API token. Instead, register this GitHub
repo as a trusted publisher: 

1. Go to <https://pypi.org/manage/kyccentral/settings/publishing/> (you must own the
   `kyccentral` project on PyPI first).
2. Click **Add a new publisher**.
3. Select **GitHub** as the publisher.
4. Fill in:
   - Repository name: your GitHub repo (e.g. `qualia91/kyc-central-client`)
   - Workflow name: `publish.yml`
   - Environment name: (leave blank, or use `pypi` if you gate releases with an
     environment in GitHub)
5. Click **Add**.

After this, any `vX.Y.Z` tag pushed to `main` from this repo can publish to PyPI — no
secrets to rotate.

### npm (trusted publishing)

npm supports [trusted publishing](https://docs.npmjs.com/trusted-publishers/) via OIDC,
just like PyPI — no API token to store or rotate. 

> ⚠️ **If you skip the one-time setup below, `npm publish --provenance` fails with
> `ENEEDAUTH` ("This command requires you to be logged in to
> https://registry.npmjs.org"). The workflow cannot fix this for you.**

1. Ensure you **own** the `@kyccentral` scope (and the `@kyccentral/sdk` package) on npm.
2. On <https://www.npmjs.com/>, go to your package settings for `@kyccentral/sdk`
   → **Trusted Publishing**.
3. Click **Add trusted publisher**.
4. Select **GitHub Actions** as the publisher and fill in:
   - Organization or user: your GitHub username (e.g. `qualia91`)
   - Repository: `kyc-central-client`
   - Workflow filename: `publish.yml`
   - Allowed actions: `npm publish` (and `npm stage publish` if you use snapshots)
5. Click **Add**.

Requirements: npm CLI 11.6+ (Node 22.14+; the publish workflow uses Node 24, which
ships npm 11.6+). The workflow's `permissions: id-token: write` lets npm exchange the
GitHub OIDC token for a short-lived npm token automatically — no `NPM_TOKEN` secret is
stored in GitHub. The workflow deliberately does **not** set `registry-url` on
`actions/setup-node`, so no `_authToken` line is ever written to `.npmrc` and npm
performs the OIDC exchange itself rather than falling back to classic auth.
`npm publish --provenance` is still used so every release is signed with an
[SLSA](https://slsa.dev/) attestation tied to this repo and the tag (the `provenance: true`
flag in `package.json` also enables this).

If OIDC trusted publishing cannot be used (e.g. the package is owned by an org that
forbids it), fall back to a classic publish token: create an **Automation** token on
npm with publish access, store it as the **`NPM_TOKEN`** repository secret, and set
`env: NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` on the publish step. With a token
present, the workflow's OIDC path is bypassed automatically.

### Hex (API key)

1. Log in to <https://hex.pm/> with your account.
2. Go to <https://hex.pm/dashboard> → **API Keys**.
3. Click **Create API Key**. Give it a descriptive name (e.g. `github-actions-publish`).
4. Select **Full access** (or at minimum `api key: publishes`).
5. Copy the key and save it as the **`HEX_API_KEY`** repository secret in GitHub:
   `Settings → Secrets and variables → Actions → New repository secret`.

## Per-release steps

Every release goes through `release.py`, run from the repository root on `main`.
Preview it first:

```bash
python release.py X.Y.Z --dry-run   # prints every planned edit; no git calls, no writes
python release.py X.Y.Z
```

`X.Y.Z` must be strictly greater than the current version. The script refuses to run
unless you are on `main` with no changes to tracked files and the tag does not already
exist. It then:

1. **Bumps all three versions** (`python/src/kyccentral/_version.py`,
   `javascript/package.json`, `javascript/package-lock.json` and
   `javascript/src/version.ts`, `elixir/mix.exs`).
2. **Rolls all three changelogs**: the `## Unreleased` entries in each client's
   `CHANGELOG.md` move under a new `## X.Y.Z — YYYY-MM-DD` heading. A client with no
   entries gets the line "No changes; version aligned with the other clients."
3. **Commits** the result as `Release vX.Y.Z`, **tags** it `vX.Y.Z`, and **pushes**
   `main` and the tag.

The `publish.yml` workflow starts automatically on the tag. It runs the full
test + lint + format + type-check suite for all three clients; each job first checks
that its package version equals the tag, and on green the package is published.

## What the publish workflow does per language

| Language | Build | Publish | Auth |
|---|---|---|---|
| Python | `python -m build` → `python/dist/` | `pypa/gh-action-pypi-publish` | OIDC trusted publishing |
| JavaScript | `npm run build` (tsup: ESM + CJS + .d.ts) | `npm publish --provenance` | OIDC trusted publishing |
| Elixir | `mix compile` (via `mix hex.publish`) | `mix hex.publish --yes` | `HEX_API_KEY` |

## Verifying a release

Wait 5–10 minutes, then check:

- PyPI: <https://pypi.org/project/kyccentral/>
- npm: <https://www.npmjs.com/package/@kyccentral/sdk>
- Hex: <https://hex.pm/packages/kyccentral>

## Notes

- **npm trusted publishing**: the `id-token: write` permission lets npm exchange the
  GitHub OIDC token for a short-lived npm token — no `NPM_TOKEN` secret is stored. The
  workflow does **not** set `registry-url` on `setup-node` and does **not** leave a
  `_authToken` line in `.npmrc`, so the npm CLI initiates the OIDC exchange itself
  instead of failing with `ENEEDAUTH` (classic-auth fallback). If npm still reports
  `ENEEDAUTH`, the trusted publisher on npmjs.com is either not configured or doesn't
  match this repo/workflow/file. `--provenance` (also set in `package.json`) generates
  an [SLSA](https://slsa.dev/) attestation linking the package to this repo and the
  release tag; npm shows a "View transparency details" link on the package page.
  Requires npm CLI 11.6+ (Node 24 ships npm 11.6).
- **PyPI trusted publishing**: requires the tag to be pushed from the default branch
  (`main`). If you publish from a fork, use an API token instead.
- **Pin action versions**: `pypa/gh-action-pypi-publish` is pinned by full commit
  SHA in `publish.yml` (currently `v1.14.2`) rather than the moving `@release/v1`
  tag. The action normalizes its inputs to kebab-case each major release (the
  `directory` input was removed and replaced by `packages-dir`), so pinning to a
  tag/SHA prevents an upstream rewrite from silently breaking your publish. If you
  deliberately keep `@release/v1`, be sure the `packages-dir` input is being used.
- **Hex key**: rotate this just like any other secret; `HEX_API_KEY` is not tied to a
  specific version. The publish step runs in the default `:dev` env (not `prod`) so
  that `ex_doc`, declared `only: :dev` in `elixir/mix.exs`, is available and
  `mix hex.publish` can generate HexDocs via the `mix docs` task.
- **Version discipline**: all three clients always share one version. A client with
  no changes still gets the bump, with a "No changes; version aligned" changelog entry;
  `release.py` does this for you.
