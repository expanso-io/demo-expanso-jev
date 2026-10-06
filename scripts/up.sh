#!/usr/bin/env bash
set -euo pipefail

exec uv run demos/11-pod-labels/scenario/local.py up
