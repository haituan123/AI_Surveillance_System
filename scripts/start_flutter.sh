#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$(uname -s)" == "Darwin" ]]; then
  default_device="macos"
else
  default_device="chrome"
fi
device="${FLUTTER_DEVICE:-$default_device}"
backend_url="${BACKEND_URL:-http://127.0.0.1:8000}"

cd "$project_root/app_flutter"
exec flutter run -d "$device" --dart-define="BACKEND_URL=$backend_url" "$@"
