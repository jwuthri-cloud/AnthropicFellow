#!/usr/bin/env bash
# Benchmark every entry of a bench config on one H100 (experiments/06_bench_models.py): a vLLM
# stage and a transformers stage per entry, each in its own process and under a time cap, with the
# HF cache (hub *and* the xet chunk cache, which otherwise keeps every model's chunks and filled a
# 250 GB disk by the third model) cleared between models. A failing entry is logged and skipped.
# Usage: experiments/run_bench_models.sh [CONFIG] [ENTRY ...]   (no entries: all of them)
set -uo pipefail
# Cost guard: hard stop after MAX_HOURS, whatever happens to the job or the laptop watching it.
sudo shutdown -h +$((60 * ${MAX_HOURS:-4})) 2>/dev/null || true
trap 'echo "=== $(date -u +%H:%M:%S) exit $?"; sudo shutdown -h +20' EXIT
cd "$(dirname "$0")/.."
export HF_HOME=${HF_HOME:-$HOME/hf} PATH=$HOME/.local/bin:$PATH
CFG=${1:-configs/22_bench_models.toml}
shift || true
ENTRIES=${*:-$(uv run python -c "import tomllib,sys; print(' '.join(e['name'] for e in tomllib.load(open(sys.argv[1],'rb'))['entries']))" "$CFG")}
for E in $ENTRIES; do
  echo "--- disk free: $(df -h --output=avail "$HOME" | tail -1)"
  echo "=== $(date -u +%H:%M:%S) $E vllm"
  timeout 50m uv run python experiments/06_bench_models.py --config "$CFG" --entry "$E" --stage vllm 2>&1 | grep -E '^\{"entry"|Error|error:' | tail -5 || echo "--- $E vllm failed"
  if uv run python -c "import tomllib,sys; e=[x for x in tomllib.load(open(sys.argv[1],'rb'))['entries'] if x['name']==sys.argv[2]][0]; sys.exit(0 if e.get('hf', True) else 1)" "$CFG" "$E"; then
    echo "=== $(date -u +%H:%M:%S) $E hf"
    timeout 25m uv run python experiments/06_bench_models.py --config "$CFG" --entry "$E" --stage hf 2>&1 | grep -E '^\{"entry"|Error|error:' | tail -5 || echo "--- $E hf failed"
  fi
  rm -rf "$HF_HOME/hub"/models--* "$HF_HOME/xet"
done
echo "=== $(date -u +%H:%M:%S) bench done"
