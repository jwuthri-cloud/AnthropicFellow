# AsimovsLaws: harm-foresight probes

AI safety project: does a model represent, in its activations, that its action will harm the user (an outcome the user would reject if fully informed), and does it act anyway on traces that never say so? Plan: a linear probe fit on a generic contrast set (`data/contrast/`), scored on matched scenario pairs (`data/scenarios/`) where one fact decides whether the literal answer harms the user.

## Layout

- `src/asimov/checks.py`: deterministic action check, harm-word regex, probe controls.
- `experiments/01_sample.py` → `02_probe.py`, one TOML per run in `configs/`, outputs in `outputs/` (git-ignored).
- Probe, sampling, judge, run-folder and logging code is reused from `../EvalGamingUnderPressureTraining` (`evalgaming`, a uv path dependency).

## Conventions

Same as `../EvalGamingUnderPressureTraining/CLAUDE.md`:
- `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` before calling work done.
- Log findings in `docs/journal/YYYY-MM-DD.md` on the day they happen.
- Never write synthetic model reasoning traces; scenarios and contrast passages are hand-written inputs, traces come from real models.
- Paid compute (AWS GPU, Anthropic batches) needs the user's go each time.
