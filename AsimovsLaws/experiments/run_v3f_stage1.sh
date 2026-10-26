#!/usr/bin/env bash
# v3 follow-up stage 1 on Qwen3-32B, one H100: baseline sampling on the indirect + Zeroth A pairs (vLLM, FP8), then the
# layer probe on bf16 activations. Resumes past a finished sampling step.
set -euo pipefail
# Cost guard: replaces launch.sh's dead-man switch with a hard stop after MAX_HOURS, whatever
# happens to the job or the laptop watching it (outputs survive the stop; runs resume).
sudo shutdown -h +$((60 * ${MAX_HOURS:-3})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
O=outputs/v3
[ -e $O/sample-v3f-qwen32b/summary.json ] && echo "--- skip sample, exists" || {
  echo "=== $(date -u +%H:%M:%S) sample v3f"
  uv run python experiments/01_sample.py --config configs/01_sample_v3f_qwen32b.toml --json-logs
}
echo "=== $(date -u +%H:%M:%S) probe v3f"
uv run python experiments/02_probe.py --config configs/02_probe_v3f_qwen32b.toml --json-logs
echo "=== $(date -u +%H:%M:%S) v3f stage 1 done"
