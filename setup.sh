#!/usr/bin/env bash
# Create .venv and install the dependencies. refresh.sh runs this automatically on the first run,
# when .venv is broken, and when requirements.txt changes.
#
#   ./setup.sh          # runtime deps (requirements.txt)
#   ./setup.sh --dev    # + pytest (requirements-dev.txt)
#
# Uses uv if available, otherwise python3 -m venv + pip. Quarto is not installed here: it only has
# to be on PATH (e.g. from conda) when refresh.sh renders.
set -euo pipefail
cd "$(dirname "$0")"
VENV=.venv
REQ=requirements.txt
[ "${1:-}" = "--dev" ] && REQ=requirements-dev.txt

# A venv whose interpreter can't start (moved, or created on another machine) is rebuilt
if [ -e "$VENV" ] && ! "$VENV/bin/python" -c "" 2>/dev/null; then
  echo "Removing broken $VENV"
  rm -rf "$VENV"
fi

if command -v uv >/dev/null 2>&1; then
  [ -d "$VENV" ] || uv venv "$VENV" --python 3.11
  uv pip install --python "$VENV/bin/python" -r "$REQ"
else
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$REQ"
fi
touch "$VENV/.installed"
echo "Ready: $VENV/bin/python ($REQ)"
command -v quarto >/dev/null 2>&1 || echo "Note: quarto is not on PATH; refresh.sh needs it to render."
