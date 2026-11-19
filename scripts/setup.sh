#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

python_command="${PYTHON_COMMAND:-}"
if [[ -z "$python_command" ]]; then
  for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && \
      [[ "$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.12" ]]; then
      python_command="$candidate"
      break
    fi
  done
fi

if [[ -z "$python_command" ]] || ! command -v "$python_command" >/dev/null 2>&1; then
  echo "Python 3.12 was not found. Install it or set PYTHON_COMMAND to its executable." >&2
  exit 1
fi

python_version="$("$python_command" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$python_version" != "3.12" ]]; then
  echo "Python 3.12 is required. Detected: $python_version" >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating Python virtual environment..."
  "$python_command" -m venv .venv
fi

echo "Installing backend dependencies..."
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r backend/requirements-dev.txt

if [[ ! -f backend/.env ]]; then
  cp backend/.env.example backend/.env
  echo "Created backend/.env from the example."
fi

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter is required but was not found on PATH." >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! xcode-select -p >/dev/null 2>&1 || ! command -v xcodebuild >/dev/null 2>&1; then
    echo "Xcode command-line tools are required for the macOS Flutter app." >&2
    exit 1
  fi
  if ! command -v pod >/dev/null 2>&1; then
    echo "CocoaPods is required for Flutter macOS plugins. Install it, then rerun setup." >&2
    exit 1
  fi
  flutter config --enable-macos-desktop
fi

echo "Installing Flutter dependencies..."
(cd app_flutter && flutter pub get)

echo "Setup complete."
echo "Backend: ./scripts/start_backend.sh"
echo "Flutter: ./scripts/start_flutter.sh"
echo "Verify: ./scripts/verify_project.sh"
