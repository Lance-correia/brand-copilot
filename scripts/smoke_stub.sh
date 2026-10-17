#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
  interpreter="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  interpreter="$ROOT/.venv/bin/python"
else
  interpreter=python3
fi
exec "$interpreter" "$ROOT/scripts/smoke_stub.py"
