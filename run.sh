#!/usr/bin/env bash
# vDeploy'u macOS/Linux'ta başlatır: http://127.0.0.1:3031
# İlk çalıştırmada .venv oluşturur ve bağımlılıkları kurar.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 veya üstü gerekli. Kurmak için:  brew install python@3.12" >&2
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "→ Sanal ortam oluşturuluyor ($PY)…"
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.deps-ok ] || [ requirements.txt -nt .venv/.deps-ok ]; then
  echo "→ Bağımlılıklar kuruluyor…"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
  touch .venv/.deps-ok
fi

export VDEPLOY_PORT="${VDEPLOY_PORT:-3031}"
echo "→ vDeploy çalışıyor: http://127.0.0.1:${VDEPLOY_PORT}  (durdurmak için Ctrl+C)"
exec .venv/bin/python -m vdeploy
