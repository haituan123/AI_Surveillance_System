#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "The local Python environment is missing. Run: ./scripts/setup.sh" >&2
  exit 1
fi

export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -m unittest discover -s backend/tests -v

cd "$project_root/app_flutter"
flutter analyze
flutter test

echo "All project checks passed."
