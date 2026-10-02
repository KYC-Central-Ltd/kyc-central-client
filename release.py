"""Release script for the kyc-central-client monorepo.

Releases are LOCKSTEP: every release bumps all three client libraries (Python,
JavaScript, Elixir) to the same version, even if a client has no changes.

Usage:
    python release.py X.Y.Z [--dry-run]

The version must be in X.Y.Z format (e.g. 0.7.0, 1.2.3) and strictly greater than
the current version in python/src/kyccentral/_version.py.

What it does:
  1. Validates the version format, that it is newer than the current version, and
     that every CHANGELOG.md has a `## Unreleased` heading. All inputs are
     validated before anything is written.
  2. Unless --dry-run, checks that the current branch is `main`, that the working
     tree has no changes to tracked files, and that the tag does not already exist.
  3. Updates version in:
     - python/src/kyccentral/_version.py  (__version__ = "X.Y.Z")
     - javascript/package.json             ("version": "X.Y.Z")
     - elixir/mix.exs                      (@version "X.Y.Z")
     - javascript/package-lock.json        (root version entries)
     - javascript/src/version.ts           (VERSION = 'X.Y.Z', sent in User-Agent)
  4. Rolls each client's CHANGELOG.md: the body under `## Unreleased` moves under a
     new `## X.Y.Z — YYYY-MM-DD` heading and a fresh empty `## Unreleased` stays
     above it. An empty Unreleased section gets the line "No changes; version
     aligned with the other clients."
  5. Commits the 5 version files and the 3 CHANGELOGs as `Release vX.Y.Z`.
  6. Tags, then pushes the current branch (`main`) and the tag to origin.
  7. The v* tag triggers publish.yml, which publishes all three clients.

--dry-run prints every planned file edit and makes NO git calls and NO file
writes (the version and changelog checks still apply).
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], **kw) -> str:
    """Run a CLI command and return stdout.  Raise on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)
    if result.returncode != 0:
        print(f"❌  Command failed: {' '.join(cmd)}")
        print(result.stderr)
        sys.exit(1)
    return result.stdout.strip()


def get_branch() -> str:
    return run(["git", "branch", "--show-current"])


def is_clean() -> bool:
    """Return True if there are no changes to tracked files."""
    out = run(["git", "status", "--porcelain", "--untracked-files=no"])
    return out == ""


def tag_exists(tag: str) -> bool:
    out = run(["git", "tag", "-l", tag])
    return out != ""


# ---------------------------------------------------------------------------
# Version bump / file edits (pure text transforms)
# ---------------------------------------------------------------------------

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PY_VERSION_RE = re.compile(r'__version__ = "([^"]+)"')
JSON_VERSION_RE = re.compile(r'"version": "([^"]+)"')
MIX_VERSION_RE = re.compile(r'@version "([^"]+)"')
TS_VERSION_RE = re.compile(r"VERSION = '([^']+)'")

EMPTY_CHANGELOG_LINE = "No changes; version aligned with the other clients."


def bump_version(version: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(version)
    if not m:
        print(f"❌  Version '{version}' is not in X.Y.Z format.")
        sys.exit(1)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def python_version_file(text: str, version: str) -> str:
    return PY_VERSION_RE.sub(f'__version__ = "{version}"', text)


def js_package_json(text: str, version: str) -> str:
    return JSON_VERSION_RE.sub(f'"version": "{version}"', text, count=1)


def elixir_mix_exs(text: str, version: str) -> str:
    return MIX_VERSION_RE.sub(f'@version "{version}"', text)


def js_version_ts(text: str, version: str) -> str:
    return TS_VERSION_RE.sub(f"VERSION = '{version}'", text, count=1)


def npm_lockjack(text: str, version: str) -> str:
    """Patch the root-level version entries in package-lock.json.

    Replaces the first two `"version"` occurrences (top-level + packages[""])
    so `npm install`/`npm publish` stays consistent with package.json.
    """
    return JSON_VERSION_RE.sub(f'"version": "{version}"', text, count=2)


UNRELEASED_RE = re.compile(r"^## Unreleased[ \t]*(?:\n|\Z)", re.MULTILINE)
NEXT_HEADING_RE = re.compile(r"^## ", re.MULTILINE)


def roll_changelog(text: str, version: str, today: str) -> tuple[str, int]:
    """Move the `## Unreleased` body under `## <version> — <today>`.

    Returns (new_text, number_of_non_blank_lines_moved).  Raises ValueError if the
    text has no `## Unreleased` heading.
    """
    m = UNRELEASED_RE.search(text)
    if not m:
        raise ValueError("no '## Unreleased' heading")
    rest = text[m.end() :]
    nxt = NEXT_HEADING_RE.search(rest)
    body = rest[: nxt.start()] if nxt else rest
    tail = rest[nxt.start() :] if nxt else ""
    body = body.strip()
    moved = len([ln for ln in body.splitlines() if ln.strip()])
    if not body:
        body = EMPTY_CHANGELOG_LINE
    new = f"{text[: m.start()]}## Unreleased\n\n## {version} — {today}\n\n{body}\n"
    if tail:
        new += f"\n{tail}"
    return new, moved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PY_VER = Path("python/src/kyccentral/_version.py")
JS_PKG = Path("javascript/package.json")
JS_LOCK = Path("javascript/package-lock.json")
JS_VERSION_TS = Path("javascript/src/version.ts")
MIX_EXS = Path("elixir/mix.exs")
CHANGELOGS = [
    Path("python/CHANGELOG.md"),
    Path("javascript/CHANGELOG.md"),
    Path("elixir/CHANGELOG.md"),
]


def current_version() -> str:
    if not PY_VER.exists():
        print(f"❌  Python version file not found: {PY_VER}")
        sys.exit(1)
    m = PY_VERSION_RE.search(PY_VER.read_text())
    if not m:
        print(f"❌  Could not read __version__ from {PY_VER}.")
        sys.exit(1)
    return m.group(1)


def first_version(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return m.group(1) if m else "?"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump all three clients to one version, roll CHANGELOGs, commit, tag and push."
    )
    parser.add_argument("version", help="new version in X.Y.Z format")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned edits; make no git calls and no file writes",
    )
    args = parser.parse_args()

    version = args.version
    dry_run: bool = args.dry_run
    new_tuple = bump_version(version)
    tag = f"v{version}"
    today = datetime.now(tz=timezone.utc).date().isoformat()

    current = current_version()
    cur_tuple = tuple(int(p) for p in current.split("."))
    if new_tuple <= cur_tuple:
        print(
            f"❌  Version {version} must be greater than the current version {current}."
        )
        sys.exit(1)

    mode = " (dry run)" if dry_run else ""
    print(f"🚀  Release script{mode} — lockstep bump {current} → {version}")

    # ---- 1. Validate inputs and compute every edit (no writes yet) ----
    for path, label in [
        (JS_PKG, "JavaScript package.json"),
        (JS_VERSION_TS, "JavaScript src/version.ts"),
        (MIX_EXS, "Elixir mix.exs"),
    ]:
        if not path.exists():
            print(f"❌  {label} not found.")
            sys.exit(1)

    edits: list[tuple[Path, str]] = []  # (path, new text)
    print("📦  Planned version edits:")

    def plan_version(path: Path, fn, pattern: re.Pattern[str]) -> None:
        text = path.read_text()
        edits.append((path, fn(text, version)))
        print(f"   ✎ {path}: {first_version(pattern, text)} → {version}")

    plan_version(PY_VER, python_version_file, PY_VERSION_RE)
    plan_version(JS_PKG, js_package_json, JSON_VERSION_RE)
    plan_version(JS_VERSION_TS, js_version_ts, TS_VERSION_RE)
    plan_version(MIX_EXS, elixir_mix_exs, MIX_VERSION_RE)
    if JS_LOCK.exists():
        plan_version(JS_LOCK, npm_lockjack, JSON_VERSION_RE)
    else:
        print("⚠️  javascript/package-lock.json not found — skipping lockfile patch.")

    print("📝  Planned changelog edits:")
    for path in CHANGELOGS:
        if not path.exists():
            print(f"❌  {path} not found.")
            sys.exit(1)
        try:
            new_text, moved = roll_changelog(path.read_text(), version, today)
        except ValueError as exc:
            print(f"❌  {path}: {exc}.")
            sys.exit(1)
        edits.append((path, new_text))
        if moved:
            detail = f"{moved} Unreleased line(s) move under it"
        else:
            detail = f"Unreleased is empty; will write '{EMPTY_CHANGELOG_LINE}'"
        print(f"   ✎ {path}: new heading '## {version} — {today}'; {detail}")

    if dry_run:
        print("\n🧪  Dry run: no git calls made and no files written.")
        return

    # ---- 2. Safety checks ----
    print("🔎  Checking branch…")
    branch = get_branch()
    if branch != "main":
        print(
            f"❌  Releases must be cut from main (currently on '{branch or 'detached HEAD'}')."
        )
        sys.exit(1)

    print("🔎  Checking working tree…")
    if not is_clean():
        print(
            "❌  Working tree has changes to tracked files. Commit or stash them first."
        )
        sys.exit(1)

    print("🔎  Checking tag availability…")
    if tag_exists(tag):
        print(f"❌  Tag {tag} already exists locally.")
        sys.exit(1)

    # ---- 3. Write files ----
    print("✍️  Writing files…")
    for path, new_text in edits:
        path.write_text(new_text)
        print(f"   ✔ {path}")

    # ---- 4. Commit ----
    print("📝  Committing release…")
    run(["git", "add", *[str(p) for p, _ in edits]])
    run(["git", "commit", "-m", f"Release v{version}"])

    # ---- 5. Tag ----
    print(f"🏷️  Creating tag {tag}…")
    run(["git", "tag", tag])

    # ---- 6. Push ----
    print(f"🚀  Pushing branch {branch} and tag {tag}…")
    run(["git", "push", "origin", branch])
    run(["git", "push", "origin", tag])

    print(f"\n✅  Release {version} complete!")
    print(
        f"   Tag {tag} has been pushed. The publish.yml workflow will run automatically."
    )


if __name__ == "__main__":
    main()
