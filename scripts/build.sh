#!/usr/bin/env bash
# Cut a release: bump pyproject.toml's version, prepend a CHANGELOG.md entry
# from commits since the last release tag, commit both, tag the release,
# then build the riva-agent image tagged with the new version and "latest".
#
# Usage:
#   ./scripts/build.sh              # bumps patch (0.1.0 -> 0.1.1)
#   ./scripts/build.sh patch        # same as above
#   ./scripts/build.sh minor        # 0.1.0 -> 0.2.0
#   ./scripts/build.sh major        # 0.1.0 -> 1.0.0
#
#   RIVA_TAG=0.1.0 docker compose up -d   # pin to a specific version
#   docker compose up -d                  # runs "latest"
#
# Requires a clean working tree: the release commit should contain only the
# version bump and changelog, not whatever else happens to be lying around.
set -euo pipefail
cd "$(dirname "$0")/.."

BUMP="${1:-patch}"
case "$BUMP" in
  patch|minor|major) ;;
  *)
    echo "Usage: $0 [patch|minor|major]" >&2
    exit 1
    ;;
esac

if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree has uncommitted changes. Commit or stash before releasing." >&2
  exit 1
fi

CURRENT_VERSION=$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/')
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

case "$BUMP" in
  patch) PATCH=$((PATCH + 1)) ;;
  minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
  major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
esac

VERSION="$MAJOR.$MINOR.$PATCH"

sed -i '' -E "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml

echo "Bumped version ($BUMP): $CURRENT_VERSION -> $VERSION"

# --- Changelog: commits since the last release tag (or all history, on the
# first-ever release) become the new top entry in CHANGELOG.md. ---
CHANGELOG="CHANGELOG.md"
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null || true)
if [ -n "$PREV_TAG" ]; then
  COMMIT_RANGE="$PREV_TAG..HEAD"
else
  COMMIT_RANGE="HEAD"
fi

ENTRY=$(git log $COMMIT_RANGE --pretty=format:'- %s (%h)' || true)
if [ -z "$ENTRY" ]; then
  ENTRY="- No changes recorded"
fi

if [ ! -f "$CHANGELOG" ]; then
  printf '# Changelog\n\n' > "$CHANGELOG"
fi

{
  printf '# Changelog\n\n'
  printf '## %s - %s\n\n' "$VERSION" "$(date +%Y-%m-%d)"
  printf '%s\n\n' "$ENTRY"
  tail -n +3 "$CHANGELOG"
} > "${CHANGELOG}.tmp"
mv "${CHANGELOG}.tmp" "$CHANGELOG"

echo "Updated $CHANGELOG"

# --- Commit + tag: keeps the tag pointing at the commit that actually
# contains the matching version, so "commits since last tag" stays accurate
# next time this script runs. ---
git add pyproject.toml "$CHANGELOG"
git commit -m "chore: release v$VERSION"
git tag "v$VERSION"

echo "Committed and tagged v$VERSION"

docker build --build-arg VERSION="$VERSION" -t "riva-agent:$VERSION" -t riva-agent:latest .

echo "Built riva-agent:$VERSION and riva-agent:latest"
