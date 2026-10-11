#!/usr/bin/env bash
# Explicit publication helper; never called by the analysis skill or installer.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null 2>&1 || { printf '需要 Python 3.9+。\n' >&2; exit 1; }
exec python3 -B "$ROOT/scripts/publish_github.py" "$@"
