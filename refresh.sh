#!/usr/bin/env bash
# Nightly: fetch data, render the dashboard, publish it. Each source fails independently.
set -uo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a

# Own .venv unless PYTHON is set: create/repair it on first run or when requirements change
if [ -z "${PYTHON:-}" ]; then
  if ! .venv/bin/python -c "" 2>/dev/null || [ requirements.txt -nt .venv/.installed ]; then
    ./setup.sh || { echo "!! setup.sh failed" >&2; exit 1; }
  fi
fi
PY=$(realpath -s "${PYTHON:-.venv/bin/python}")

status=0
for mod in ingest.tally ingest.github ingest.packages ingest.discord_snapshot; do
  "$PY" -m "$mod" || { echo "!! $mod failed" >&2; status=1; }
done

# Render with whatever data we have, even if one source failed today
command -v quarto >/dev/null 2>&1 || { echo "!! quarto not on PATH (activate the conda env that has it)" >&2; exit 1; }
(cd dashboard && QUARTO_PYTHON="$PY" quarto render index.qmd) || exit 1

if [ -n "${DEPLOY_DIR:-}" ]; then
  mkdir -p "$DEPLOY_DIR"
  rsync -a --delete dashboard/index.html dashboard/index_files "$DEPLOY_DIR"/
fi
exit $status
