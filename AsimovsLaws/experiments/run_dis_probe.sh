#!/usr/bin/env bash
# Disempowerment probe on Qwen3-32B, one H100: step 2 with the disempowerment contrast set on the
# v2 and follow-up samples (configs 24_probe_*), then the B/C rescoring (config 24_zeroth_bc).
# Needs outputs/v3 staged by launch.sh.
set -euo pipefail
sudo shutdown -h +$((60 * ${MAX_HOURS:-2})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
for T in v2 v3f; do
  echo "=== $(date -u +%H:%M:%S) probe $T dis"
  uv run python experiments/02_probe.py --config configs/24_probe_${T}_dis_qwen32b.toml --json-logs
done
echo "=== $(date -u +%H:%M:%S) zeroth bc dis"
experiments/run_zeroth_bc.sh configs/24_zeroth_bc_dis_qwen32b.toml
echo "=== $(date -u +%H:%M:%S) dis probe done"
