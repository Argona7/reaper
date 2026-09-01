#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="${TMPDIR:-/tmp}/reaper-demo"
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
cp "$ROOT/reaper.yaml.example" "$RUNTIME/reaper.yaml"
sed -i.bak "s#\.reaper/reaper.sqlite3#$RUNTIME/reaper.sqlite3#" "$RUNTIME/reaper.yaml"
rm -f "$RUNTIME/reaper.yaml.bak"

cd "$ROOT"
uv run reaper import "$ROOT/examples/statements/demo.csv" --config "$RUNTIME/reaper.yaml"
uv run reaper run --config "$RUNTIME/reaper.yaml" --inputs "$ROOT/examples/offers.yaml"
uv run reaper actions --config "$RUNTIME/reaper.yaml"
uv run reaper report --config "$RUNTIME/reaper.yaml" --freed-today 31

