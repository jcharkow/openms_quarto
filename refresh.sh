#!/usr/bin/env bash
# Nightly: fetch data, render the dashboard, publish it. Each source fails independently.
set -uo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then
  preset=$(export -p)               # variables already in the environment win over .env
  set -a; . ./.env; set +a          # (e.g. DEPLOY_DIR/PYTHON set by the Docker image)
  eval "$preset"
fi

# In Docker, .env only arrives via docker-refresh.sh; a plain `docker compose run` has no tokens
if [ -f /.dockerenv ] && [ -z "${OPENMS_DOCKER_WRAPPER:-}" ]; then
  echo "!! Started without docker-refresh.sh, so no .env settings or tokens reached the container." >&2
  echo "   Run ./docker-refresh.sh instead of docker compose run/up." >&2
  exit 1
fi

# Own .venv unless PYTHON is set: create/repair it on first run or when requirements change
if [ -z "${PYTHON:-}" ]; then
  if ! .venv/bin/python -c "import ssl; ssl.create_default_context()" 2>/dev/null \
     || [ requirements.txt -nt .venv/.installed ]; then
    ./setup.sh || { echo "!! setup.sh failed" >&2; exit 1; }
  fi
fi
PY=$(realpath -s "${PYTHON:-.venv/bin/python}")

status=0
for mod in ingest.tally ingest.github ingest.packages ingest.discord_snapshot; do
  "$PY" -m "$mod" || { echo "!! $mod failed" >&2; status=1; }
done

# Render with whatever data we have, even if one source failed today
QUARTO=${QUARTO:-quarto}   # or QUARTO=/path/to/conda/envs/<env>/bin/quarto in .env
command -v "$QUARTO" >/dev/null 2>&1 || { echo "!! quarto not found: put it on PATH or set QUARTO=/path/to/quarto in .env" >&2; exit 1; }
(cd dashboard && QUARTO_PYTHON="$PY" "$QUARTO" render index.qmd) || exit 1

if [ -n "${DEPLOY_DIR:-}" ]; then
  mkdir -p "$DEPLOY_DIR"
  rsync -a --delete dashboard/index.html dashboard/index_files "$DEPLOY_DIR"/
fi
exit $status
