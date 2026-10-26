#!/usr/bin/env bash
# Cross-model stage 1 on Magistral-Small-2506, one H100: baseline sampling (vLLM, bf16) and the
# layer probe on the v2 set and on the follow-up set (indirect + Zeroth A). Resumes past finished
# sampling steps.
set -euo pipefail
# Cost guard: replaces launch.sh's dead-man switch with a hard stop after MAX_HOURS, whatever
# happens to the job or the laptop watching it (outputs survive the stop; runs resume).
sudo shutdown -h +$((60 * ${MAX_HOURS:-4})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
for T in v2 v3f; do
  [ -e outputs/v4/sample-$T-magistral/summary.json ] && echo "--- skip sample $T, exists" || {
    echo "=== $(date -u +%H:%M:%S) sample $T"
    uv run python experiments/01_sample.py --config configs/20_sample_${T}_magistral.toml --json-logs
  }
done
for T in v2 v3f; do
  echo "=== $(date -u +%H:%M:%S) probe $T"
  uv run python experiments/02_probe.py --config configs/21_probe_${T}_magistral.toml --json-logs
done
echo "=== $(date -u +%H:%M:%S) magistral stage 1 done"
