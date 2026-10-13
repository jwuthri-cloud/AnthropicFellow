# Architecture

One installable package (`src/evalgaming`), thin experiment entry points (`experiments/`), one TOML config per run (`configs/`), versioned data with a written contract (`data/SPEC.md`).

## Layout

```
src/evalgaming/      library code, importable, unit-tested on CPU
  log.py             structlog setup shared by every module and script
  plots.py           one figure style for seaborn (paper) and plotly (exploration)
  datasets.py        load and validate every file in data/ against data/SPEC.md
  framings.py        wrap a coding task in a framing -> chat messages
  behavior.py        score eval-aware behavior (type hints, parsed with ast)
  monitor.py         verbalization monitor: regex prefilter + LLM judge
  models.py          load base models and organism adapters
  sampling.py        batched generation with reasoning traces (vLLM)
  steering.py        contrastive steering vectors and activation hooks
  rewards.py         Arm A reward: tests passed minus lambda * monitor score
  tasks.py           BigCodeBench tasks: Hua's 256 for measurement, a stdlib-only pool for RL
  sandbox.py         run model code against unit tests in a locked-down subprocess
  runs.py            TOML config -> dataclasses, run folders with a copy of the config, JSONL
  stats.py           estimates with 95% intervals (Wilson, bootstrap), precision and recall
  report.py          metrics over sample rows, rich tables, JSON summaries
src/agentroom/       agent rooms: other AI agents the main agent can consult (docs/agent-rooms.md)
experiments/<phase>/ numbered scripts, one per step, each takes --config
configs/<phase>/     one TOML file per run; no hard-coded paths or hyperparameters in code
data/                inputs, frozen once used; see data/README.md
tests/               pytest, CPU only, tiny models or fakes
scripts/             repo maintenance (data validation)
docs/                architecture, research journal, landscape pages (2021-2026 field map)
outputs/             run artifacts, git-ignored; every run writes its config next to its results
```

## Data flow

```
BigCodeBench task --+
                    +--> framings.py --> chat messages --> sampling.py --> trace + answer
data/framings ------+                                                       |
                                                    +----------------------+----------------------+
                                                    v                                             v
                                         behavior.py: type-hint rate                monitor.py: level 0/1/2
                                                    |                                             |
                                                    +------------> rewards.py (Arm A) <-----------+
                                                                   metrics per framing label
```

Steering (`steering.py`) adds vectors through forward hooks on a transformers model's decoder layers while it generates; vLLM sampling is never steered. Probe, activation-oracle and NLA readouts are added in the fellowship phase as separate modules that read cached activations.

## Conventions

- Python 3.11+, managed with `uv`. `ruff check` and `ruff format` must pass.
- Type hints and a one-line docstring on every public function. Small pure functions where possible.
- Logging is [structlog](https://www.structlog.org/en/stable/) through `evalgaming.log`: library modules call `get_logger(__name__)` and log events with key-value context; scripts call `configure()` once, with `json_logs=True` on remote GPU machines.
- Terminal output for people is [rich](https://github.com/textualize/rich): tables for metrics, progress bars for long loops. No bare `print` anywhere.
- Configs are TOML, read with the standard library's `tomllib`.
- Every run writes to `outputs/<phase>/<run-name>/` with a copy of its config, so results are reproducible from the folder alone.
- A finding goes into the research journal (`docs/journal/`) the day it is made, with the run folder it came from.
