#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python_command="python3"
if [[ -x .venv/bin/python ]]; then
  python_command=".venv/bin/python"
fi

exec "$python_command" -m uvicorn backend.main:app \
  --host "${BACKEND_HOST:-127.0.0.1}" \
  --port "${BACKEND_PORT:-8000}" \
  "$@"
