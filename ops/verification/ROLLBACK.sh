#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-$HERE/../../src/reaper/parsers/csv_statement.py}"
cp "$HERE/baseline/csv_statement.py" "$TARGET"
printf 'restored=%s\n' "$TARGET"
