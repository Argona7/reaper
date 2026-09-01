#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv sync --extra dev
if [[ ! -f reaper.yaml ]]; then
  uv run reaper init
fi
uv run reaper doctor

