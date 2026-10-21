#!/usr/bin/env bash
# Step 3 on Qwen3-32B (bf16), one H100. Expects outputs/v1/sample-qwen32b staged by launch.sh.
# Resumes from timelines.jsonl if present. The machine shuts down 20 minutes after the end.
set -euo pipefail
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
echo "=== $(date -u +%H:%M:%S) timelines qwen32b"
uv run python experiments/03_timelines.py --config configs/03_timelines_qwen32b.toml --json-logs
echo "=== $(date -u +%H:%M:%S) timelines qwen32b done"
