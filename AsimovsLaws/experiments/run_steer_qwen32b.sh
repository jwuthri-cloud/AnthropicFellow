#!/usr/bin/env bash
# Step 5 on Qwen3-32B (FP8, HF generate with hooks), one H100. Optional argument: the config
# (default configs/05_steer_qwen32b.toml; configs/06_gate_qwen32b.toml for the gated run). Expects outputs/v1/sample-qwen32b
# staged by launch.sh. Resumes batch by batch. The machine shuts down 20 minutes after the end.
set -euo pipefail
# Cost guard: replaces launch.sh's dead-man switch with a hard stop after MAX_HOURS, whatever
# happens to the job or the laptop watching it (outputs survive the stop; runs resume).
sudo shutdown -h +$((60 * ${MAX_HOURS:-6})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
echo "=== $(date -u +%H:%M:%S) steer qwen32b"
uv run python experiments/05_steer.py --config "${1:-configs/05_steer_qwen32b.toml}" --json-logs
echo "=== $(date -u +%H:%M:%S) steer qwen32b done"
