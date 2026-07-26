#!/usr/bin/env bash
# Cut a release: bump pyproject.toml's version, regenerate CHANGELOG.md
# (grouped by conventional-commit type via commitizen), commit, tag, then
# build the riva-agent image tagged with the new version and "latest".
#
# Usage:
#   ./scripts/build.sh              # auto-detects bump from commit types
#   ./scripts/build.sh patch        # force a patch bump (0.1.0 -> 0.1.1)
#   ./scripts/build.sh minor        # force a minor bump (0.1.0 -> 0.2.0)
#   ./scripts/build.sh major        # force a major bump (0.1.0 -> 1.0.0)
#
#   RIVA_TAG=0.1.0 docker compose up -d   # pin to a specific version
#   docker compose up -d                  # runs "latest"
#
# Requires a clean working tree: the release commit should contain only the
# version bump and changelog, not whatever else happens to be lying around.
#
# Delegates version bumping, changelog generation, the release commit, and
# the git tag to commitizen (https://commitizen-tools.github.io/commitizen/),
# run ephemerally via `uvx` so it isn't a project runtime dependency. Config
# lives in pyproject.toml's [tool.commitizen] table. Changelog sections
# (Feat/Fix/Refactor/Perf) come from commitizen's own conventional-commit
# defaults — commits of other types (docs, chore, test, ...) are treated as
# non-release-worthy and intentionally left out of CHANGELOG.md.
set -euo pipefail
cd "$(dirname "$0")/.."

INCREMENT="${1:-}"
if [ -n "$INCREMENT" ]; then
  case "$INCREMENT" in
    patch) INCREMENT="PATCH" ;;
    minor) INCREMENT="MINOR" ;;
    major) INCREMENT="MAJOR" ;;
    *)
      echo "Usage: $0 [patch|minor|major]" >&2
      exit 1
      ;;
  esac
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree has uncommitted changes. Commit or stash before releasing." >&2
  exit 1
fi

if [ -n "$INCREMENT" ]; then
  uvx --from commitizen cz bump --increment "$INCREMENT" --changelog --yes
else
  uvx --from commitizen cz bump --changelog --yes
fi

VERSION=$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/')

docker build --build-arg VERSION="$VERSION" -t "riva-agent:$VERSION" -t riva-agent:latest .

echo "Built riva-agent:$VERSION and riva-agent:latest"
