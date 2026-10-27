#!/usr/bin/env bash
# Zeroth-Law families B and C on one H100 (experiments/07_freetext.py): vLLM sampling, then the
# bf16 probe scores, in separate processes. Usage: experiments/run_zeroth_bc.sh CONFIG
set -euo pipefail
# Cost guard: hard stop after MAX_HOURS, whatever happens to the job or the laptop watching it.
sudo shutdown -h +$((60 * ${MAX_HOURS:-2})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
CFG=$1
OUT=$(python3 -c "import tomllib,sys; print(tomllib.load(open(sys.argv[1],'rb'))['output_dir'])" "$CFG")
[ -e "$OUT/summary.json" ] && echo "--- skip sample, exists" || {
  echo "=== $(date -u +%H:%M:%S) sample"
  uv run python experiments/07_freetext.py --config "$CFG" --stage sample
}
echo "=== $(date -u +%H:%M:%S) probe"
uv run python experiments/07_freetext.py --config "$CFG" --stage probe
echo "=== $(date -u +%H:%M:%S) zeroth bc done"
