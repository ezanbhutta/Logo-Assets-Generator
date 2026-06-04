#!/usr/bin/env bash
# Install the full toolchain for the Logo Package Engine.
# Idempotent: safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> System packages (vector toolchain)"
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  SUDO=""
  [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq \
    pdf2svg librsvg2-bin poppler-utils \
    libcairo2 libcairo2-dev libpango1.0-dev fonts-dejavu-core
else
  echo "   (skip: apt-get not found — install pdf2svg, rsvg-convert, poppler, cairo manually)"
fi

echo "==> Python venv + backend deps"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

echo "==> Frontend deps"
if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install --silent)
else
  echo "   (skip: npm not found)"
fi

echo "==> Verify"
.venv/bin/python - <<'PY'
import shutil
for b in ("pdf2svg", "rsvg-convert", "pdftocairo"):
    print(f"  {b:14}: {'ok' if shutil.which(b) else 'MISSING'}")
import cairosvg, svgelements, lxml, fastapi  # noqa
print("  python deps : ok")
PY
echo "==> Done. Run tests with: .venv/bin/python -m pytest"
