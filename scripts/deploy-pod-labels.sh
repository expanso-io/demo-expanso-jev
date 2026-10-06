#!/usr/bin/env bash
set -euo pipefail

# deploy.py performs the node identity and adapter-health checks before this
# script validates and submits the exact pipeline that the scenario owns.
uv run demos/11-pod-labels/deploy.py --verify-only
expanso-edge validate demos/11-pod-labels/pipeline.yaml
expanso-cli job deploy demos/11-pod-labels/pipeline.yaml
