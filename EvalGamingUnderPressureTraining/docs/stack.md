# Stack

Which existing package covers each need, so no time goes into rebuilding what already works. Decided 2026-10-13. Change a row only with a journal entry saying why.

## In use now

| Need | Package | Why this one |
| --- | --- | --- |
| Environment and dependencies | [uv](https://docs.astral.sh/uv/) | Fast, lockfile, one command to reproduce the environment on a GPU box |
| Lint and format | [ruff](https://docs.astral.sh/ruff/) | One tool for both, near-instant |
| Tests | pytest | Standard; CPU-only tests keep it runnable anywhere |
| Logging | [structlog](https://www.structlog.org/en/stable/) | Key-value events; JSON lines on remote runs, readable console locally |
| Terminal output | [rich](https://github.com/textualize/rich) | Tables, progress bars and tracebacks people can read |
| Command-line entry points | [Typer](https://typer.tiangolo.com/) | Options from type hints, rich help, less boilerplate than argparse |
| Configs | `tomllib` (standard library) + dataclasses | No dependency; TOML is readable and diff-friendly |
| LLM judge (verbalization monitor) | [anthropic](https://github.com/anthropics/anthropic-sdk-python) SDK with `claude-haiku-5-5` | Schema-constrained JSON via `output_config.format`, prompt caching of the rubric, built-in retries, Message Batches at 50% cost for offline scoring |
| Tables and stats | numpy, pandas, [SciPy](https://scipy.org/) | `scipy.stats.bootstrap` gives confidence intervals without hand-written resampling |
| Probes | [scikit-learn](https://scikit-learn.org/) | Logistic-regression probes, AUROC and cross-validation in a few lines |
| Paper figures | [seaborn](https://seaborn.pydata.org/) | Statistical plots with confidence intervals built in |
| Interactive figures | [plotly](https://plotly.com/python/) | Hover and zoom for exploring results; standalone HTML per run |
| Agent rooms for the main agent | [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.x (`MCPServer`) | Claude Code's native way to get new tools |
| Room seats on subscriptions | Claude Code CLI (`claude -p`) and Codex CLI (`codex exec`) | No per-call cost; read-only flags enforced per call |
| Room seats on API models | [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) with OpenRouter | Any model, read-only repo mount, permission rules |

`src/evalgaming/plots.py` gives both plotting libraries one style, so a framing label has the same color in every figure.

## On the GPU machine (`gpu` extra)

| Need | Package | Why this one |
| --- | --- | --- |
| Fast sampling with reasoning traces | [vLLM](https://docs.vllm.ai/) | Batched generation an order of magnitude faster than plain transformers |
| Model loading, hooks for steering | [transformers](https://huggingface.co/docs/transformers) + plain PyTorch forward hooks | Steering is a few lines of hook code; no wrapper library needed |
| LoRA adapters | [PEFT](https://huggingface.co/docs/peft) | Loads the organism's adapter stack and trains new adapters |
| RL (pilot, 4B to 8B) | [TRL](https://huggingface.co/docs/trl) `GRPOTrainer` | Simplest GRPO with vLLM generation and LoRA; final choice recorded in `docs/pilot.md` |
| RL (fellowship, 27B and multi-node) | [verl](https://github.com/volcengine/verl) | Scales to multi-node FSDP or Megatron with vLLM or SGLang rollouts |
| Experiment tracking | [Weights & Biases](https://wandb.ai/) | TRL and verl report to it natively; reward curves and samples per step |
| Datasets | Hugging Face [datasets](https://huggingface.co/docs/datasets) | Loads Montoya's and Hua's released data directly |

## Fellowship phase, from released code

| Need | Source | Note |
| --- | --- | --- |
| Natural language autoencoders | [kitft/natural_language_autoencoders](https://github.com/kitft/natural_language_autoencoders) | Released checkpoints for Gemma-3-27B and others; training recipe for a Qwen3-8B NLA |
| Activation oracles | [adamkarvonen/activation_oracles](https://github.com/adamkarvonen/activation_oracles) | Released checkpoints for Qwen3-8B and Gemma-3-27B |
| Sparse autoencoders and transcoders | [SAELens](https://github.com/jbloomAus/SAELens) with [Gemma Scope 2](https://huggingface.co/google/gemma-scope-2-27b-it) | For the Gemma-3-27B confirmation runs |
| Steering-gaming baseline | [Hua et al. code](https://github.com/tim-hua-01/steering-eval-awareness-public) | Steering vectors and the 49B organism |
| Unverbalized eval-awareness baseline | [Montoya et al. code](https://github.com/lmmontoya-ai/Non-verbal-Eval-Awareness) | Probes, resampling and the Qwen3.5-4B organism |
| GPU machines | [RunPod](https://www.runpod.io/), with [SkyPilot](https://docs.skypilot.co/) if multi-node runs need it | RunPod is already connected; SkyPilot only if 27B runs span several nodes |

## Considered and not adopted

| Package | Why not, for now |
| --- | --- |
| [Inspect](https://inspect.aisi.org.uk/) (UK AISI) | Our scoring runs inside the RL reward loop, so Inspect would wrap code we need anyway. Revisit for Petri-style agentic audits. |
| TransformerLens, nnsight | Plain forward hooks cover steering and activation caching on Hugging Face models. Revisit if activation patching across many layers becomes central. |
| Tinker (managed LoRA training) | Montoya et al. used it and it could speed up organism building, but pricing is unverified and model support changes. Revisit when building the Qwen3-8B organism. |
| polars | pandas is required by seaborn anyway; one dataframe library is enough. |
| pydantic for configs | Dataclasses plus TOML are enough today. pydantic is already present through the anthropic SDK if config validation becomes a problem. |
