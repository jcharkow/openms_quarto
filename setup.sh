#!/usr/bin/env bash
# Create .venv and install the dependencies. refresh.sh runs this automatically on the first run,
# when .venv is broken, and when requirements.txt changes.
#
#   ./setup.sh          # runtime deps (requirements.txt)
#   ./setup.sh --dev    # + pytest (requirements-dev.txt)
#
# Uses uv if available (on the system Python, so the system OpenSSL config is understood),
# otherwise python3 -m venv + pip. Quarto is not installed here: refresh.sh finds it on PATH or via
# QUARTO=/path/to/quarto in .env.
set -euo pipefail
cd "$(dirname "$0")"
VENV=.venv
REQ=requirements.txt
[ "${1:-}" = "--dev" ] && REQ=requirements-dev.txt

# A venv whose interpreter can't start or can't do SSL is rebuilt. (uv's downloaded Pythons bundle an
# OpenSSL that may reject the system /etc/ssl/openssl.cnf: "SSLError: error in system default config")
if [ -e "$VENV" ] && ! "$VENV/bin/python" -c "import ssl; ssl.create_default_context()" 2>/dev/null; then
  echo "Removing broken $VENV (interpreter or SSL not working)"
  rm -rf "$VENV"
fi

if command -v uv >/dev/null 2>&1; then
  [ -d "$VENV" ] || uv venv "$VENV" --python-preference only-system \
    || uv venv "$VENV" --python 3.11   # no usable system Python: fall back to a uv-managed one
  uv pip install --python "$VENV/bin/python" -r "$REQ"
else
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip
  "$VENV/bin/python" -m pip install -r "$REQ"
fi
touch "$VENV/.installed"
echo "Ready: $VENV/bin/python ($REQ)"
command -v quarto >/dev/null 2>&1 || echo "Note: quarto is not on PATH; refresh.sh needs it to render."
