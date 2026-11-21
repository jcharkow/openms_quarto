#!/usr/bin/env bash
# One dashboard refresh in Docker (ingest + render -> ./site). Use this for cron too.
#
#   ./docker-refresh.sh                 # = docker compose run --rm dashboard
#   ./docker-refresh.sh bash            # shell inside the container, for debugging
#
# Runs the container as your own user so data/ and site/ stay owned by you, and rebuilds the image
# from cache first (fast when nothing changed; picks up a git pull).
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Missing .env: cp .env.example .env and fill it in (see README)" >&2; exit 1; }
mkdir -p data "${SITE_DIR:-site}"

if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
  export HOST_UID=0 HOST_GID=0          # rootless Docker: container root maps to you on the host
else
  export HOST_UID=$(id -u) HOST_GID=$(id -g)
fi

docker compose build --quiet
exec docker compose run --rm dashboard "$@"
