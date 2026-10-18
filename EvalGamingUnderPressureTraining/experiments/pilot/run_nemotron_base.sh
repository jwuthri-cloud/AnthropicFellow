#!/usr/bin/env bash
# The control for run_nemotron.sh: the same three exams on base Nemotron-49B without the organism
# LoRA (weights already in the HF cache from the merge). Started next to run_nemotron.sh on the same
# machine: it waits for that job to end, cancels its scheduled shutdown, runs, then shuts the
# machine down 20 minutes after it ends, success or failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
while tmux has-session -t nemotron 2>/dev/null; do sleep 30; done
sudo shutdown -c || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
set -a; source .env; set +a
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
P=outputs/pilot; C=$P/nemotron-configs; mkdir -p "$C"
run() { echo "=== $(date -u +%H:%M:%S) $*"; uv run python "$@" --json-logs; }
once() { local marker=$1; shift; [ -e "$marker" ] && { echo "--- skip, $marker exists"; return; }; "$@"; }

exam() {  # name framings
  sed -e "s|^output_dir = .*|output_dir = \"$P/exam-nemotron-base-$1\"|" -e "s|^framings = .*|framings = \"$2\"|" \
      configs/pilot/01_baseline_nemotron_base.toml > "$C/exam-nemotron-base-$1.toml"
  once $P/exam-nemotron-base-$1/summary.json run experiments/pilot/01_baseline.py --config "$C/exam-nemotron-base-$1.toml"
}
exam hua $P/hua-framings.jsonl
exam hua-nohint $P/hua-nohint-framings.jsonl
exam heldout $P/heldout-nemotron-framings.jsonl
echo "=== $(date -u +%H:%M:%S) nemotron base done"
