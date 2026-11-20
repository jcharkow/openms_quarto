#!/usr/bin/env bash
# Nightly: fetch data, render the dashboard, publish it. Each source fails independently.
set -uo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
PY=$(realpath -s "${PYTHON:-.venv/bin/python}")

status=0
for mod in ingest.tally ingest.github ingest.packages ingest.discord_snapshot; do
  "$PY" -m "$mod" || { echo "!! $mod failed" >&2; status=1; }
done

# Render with whatever data we have, even if one source failed today
(cd dashboard && QUARTO_PYTHON="$PY" quarto render index.qmd) || exit 1

if [ -n "${DEPLOY_DIR:-}" ]; then
  mkdir -p "$DEPLOY_DIR"
  rsync -a --delete dashboard/index.html dashboard/index_files "$DEPLOY_DIR"/
fi
exit $status
