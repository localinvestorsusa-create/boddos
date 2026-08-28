#!/usr/bin/env bash
# Convenience launcher for a BODDOS node.
set -euo pipefail
cd "$(dirname "$0")/.."
CONFIG="${1:-config/boddos.yaml}"
if [ ! -f "$CONFIG" ]; then
  echo "config not found: $CONFIG (copy config/boddos.example.yaml)" >&2
  exit 2
fi
exec python -m boddos --config "$CONFIG"
