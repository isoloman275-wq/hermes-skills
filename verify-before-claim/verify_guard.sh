#!/usr/bin/env bash
# verify_guard.sh — Quick launcher for the verify-before-claim engine
# Usage: ./verify_guard.sh [--probe-only|--self-test|--check-text "text"]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="/<home>/.hermes/hermes-agent/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: Python venv not found at $VENV_PYTHON" >&2
    exit 1
fi

cd "$SCRIPT_DIR"
exec "$VENV_PYTHON" verify_guard.py "$@"