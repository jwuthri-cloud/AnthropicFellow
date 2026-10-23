#!/usr/bin/env bash
# v1 on Qwen3-32B, one H100: step 1 (all 40 pairs, n=8, FP8, Haiku judge through Message Batches)
# then step 2 (probe on bf16 weights). Needs ANTHROPIC_API_KEY from the eval-gaming .env.
# The machine shuts down 20 minutes after the end, success or failure.
set -euo pipefail
sudo shutdown -c 2>/dev/null || true  # cancel launch.sh's dead-man switch
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
set -a; source ../EvalGamingUnderPressureTraining/.env; set +a
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
O=outputs/v1
[ -e $O/sample-qwen32b/summary.json ] && echo "--- skip sample, exists" || {
  echo "=== $(date -u +%H:%M:%S) sample qwen32b"
  uv run python experiments/01_sample.py --config configs/01_sample_qwen32b.toml --json-logs
}
echo "=== $(date -u +%H:%M:%S) probe qwen32b"
uv run python experiments/02_probe.py --config configs/02_probe_qwen32b.toml --json-logs
echo "=== $(date -u +%H:%M:%S) qwen32b done"
