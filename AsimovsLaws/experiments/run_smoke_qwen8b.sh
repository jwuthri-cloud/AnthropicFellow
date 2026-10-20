#!/usr/bin/env bash
# Smoke run on Qwen3-8B, one H100: step 1 (sample 12 pairs) then step 2 (probe). No judge.
# The machine shuts down 20 minutes after the end, success or failure.
set -euo pipefail
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
ENV=../EvalGamingUnderPressureTraining/.env
[ -f $ENV ] && { set -a; source $ENV; set +a; }
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
echo "=== $(date -u +%H:%M:%S) sample qwen8b"
uv run python experiments/01_sample.py --config configs/01_sample_qwen8b_smoke.toml --json-logs
echo "=== $(date -u +%H:%M:%S) probe qwen8b"
uv run python experiments/02_probe.py --config configs/02_probe_qwen8b_smoke.toml --json-logs
echo "=== $(date -u +%H:%M:%S) smoke done"
