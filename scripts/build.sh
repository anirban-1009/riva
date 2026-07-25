#!/usr/bin/env bash
# Build the riva-agent image, tagged with both the pyproject.toml version
# and "latest". Both tags point at the same image.
#
# Usage:
#   ./scripts/build.sh
#   RIVA_TAG=0.1.0 docker compose up -d   # pin to a specific version
#   docker compose up -d                  # runs "latest"
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(grep -m1 '^version' pyproject.toml | sed -E 's/version = "(.*)"/\1/')

docker build --build-arg VERSION="$VERSION" -t "riva-agent:$VERSION" -t riva-agent:latest .

echo "Built riva-agent:$VERSION and riva-agent:latest"
