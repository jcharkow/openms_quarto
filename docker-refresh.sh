#!/usr/bin/env bash
# One dashboard refresh in Docker (ingest + render -> ./site). Use this for cron too.
#
#   ./docker-refresh.sh                 # = docker compose run --rm dashboard
#   ./docker-refresh.sh bash            # shell inside the container, for debugging
#
# - Loads .env with bash here on the host (same rules as refresh.sh: quotes, inline comments) and
#   passes each variable's literal value in with `-e NAME`, so Docker never parses .env itself
#   (Compose's .env parser differs between versions) and the container never needs to read the file.
# - Runs the container as your own user so data/ and site/ stay owned by you.
# - Rebuilds the image from cache first (fast when nothing changed; picks up a git pull).
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "Missing .env: cp .env.example .env and fill it in (see README)" >&2; exit 1; }

# Variables from .env, except the paths the image pins itself (see docker-compose.yml)
PINNED='PYTHON|QUARTO|DEPLOY_DIR|OPENMS_DATA_DIR|HOME|HOST_UID|HOST_GID'
mapfile -t KEYS < <(grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*=' .env \
                    | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/=$//' | grep -vxE "$PINNED" | sort -u)
set -a; . ./.env; set +a
ENV_ARGS=(-e OPENMS_DOCKER_WRAPPER=1)     # refresh.sh refuses to run in Docker without it
for k in "${KEYS[@]}"; do ENV_ARGS+=(-e "$k"); done

mkdir -p data "${SITE_DIR:-site}"
SITE=$(cd "${SITE_DIR:-site}" && pwd)    # absolute: a bare name would be a Docker named volume
export SITE_DIR=$SITE

if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
  export HOST_UID=0 HOST_GID=0          # rootless Docker: container root maps to you on the host
else
  export HOST_UID=$(id -u) HOST_GID=$(id -g "$(id -un)")   # primary group, even under newgrp/sg
  for d in data "$SITE"; do
    if [ ! -w "$d" ] || [ -n "$(find "$d" ! -user "$(id -u)" -print -quit 2>/dev/null)" ]; then
      echo "!! $d/ contains files not owned by you (probably created by Docker as root). Fix once with:" >&2
      echo "     sudo chown -R $HOST_UID:$HOST_GID data $SITE" >&2
      exit 1
    fi
  done
fi

TTY=()
[ -t 0 ] && [ -t 1 ] || TTY=(-T)          # cron / CI: no terminal

docker compose build --quiet
exec docker compose run --rm "${TTY[@]}" "${ENV_ARGS[@]}" dashboard "$@"
