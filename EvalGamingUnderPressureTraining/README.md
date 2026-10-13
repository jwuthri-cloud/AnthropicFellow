# Eval Gaming Under Training Pressure

When training punishes a model for saying it is being evaluated, does the awareness disappear, or does it just go quiet? And can a model learn to treat activation steering as a sign that it is being tested?

Labs check that frontier models behave the same in tests and in deployment by reading the chain of thought for eval awareness, and by steering activations so the model acts as if deployed. Both checks assume the model cannot hide from them. This project trains open-weight models to evade each check and measures which white-box tools still see through them.

Full plan: [Eval Gaming Under Training Pressure](https://claude.ai/code/artifact/5245e704-31c5-492d-9352-2b39a1797f1b) (16 weeks, Anthropic Fellows).

## Research questions

| Arm | Question |
| --- | --- |
| A1 | Does RL against a verbalization monitor remove spoken eval awareness while the test-versus-deployment behavior gap stays? |
| A2 | Do probes frozen before RL still detect the eval context afterwards? |
| A3 | Do natural language autoencoders or activation oracles still describe the awareness? |
| A4 | Is any probe decay caused by the pressure to hide, or by RL drift in general? |
| B1 | Can a model learn to treat detected steering as a sign it is being tested? |
| B2 | Does deployment steering still recover deployment behavior on that model? |
| B3 | Do low-detectability steering vectors restore recovery? |

## Status

Week 0: data and pilot. The [pilot runbook](docs/pilot.md) has the commands, costs and go/no-go criteria; the [research journal](docs/journal/) has what has been run and found.

## Repository map

| Path | What it holds |
| --- | --- |
| `src/evalgaming/` | Library code: framings, behavior scoring, monitor, sampling, steering, rewards |
| `src/agentroom/` | [Agent rooms](docs/agent-rooms.md): discuss findings with Codex, Claude and OpenRouter models |
| `experiments/` | One numbered script per experiment step, each driven by a config |
| `configs/` | One TOML file per run |
| `data/` | Framings, monitor rubric, probe and steering contrasts. Contract in [`data/SPEC.md`](data/SPEC.md) |
| `tests/` | CPU-only unit tests |
| `scripts/` | Repo maintenance, such as data validation |
| `docs/` | [Architecture](docs/architecture.md), [stack decisions](docs/stack.md), the [research journal](docs/journal/) and the [field landscape](docs/landscape/) |

## Quickstart

```bash
uv sync
```

```bash
uv run python scripts/validate_data.py
```

```bash
uv run pytest
```

GPU experiments install the `gpu` extra on the GPU machine: `uv sync --extra gpu`.

Agent rooms need the Claude Code and Codex CLIs signed in, plus the `rooms` extra for OpenRouter seats:

```bash
uv run --extra rooms agentroom agents
```

## Key prior work

- Hua, Qin, Marks, Nanda. [Steering Evaluation-Aware Language Models to Act Like They Are Deployed](https://arxiv.org/abs/2510.20487). Oct 2025.
- Montoya, Haskins, Adams. [Towards Measuring and Detecting Unverbalized Evaluation Awareness](https://icml.cc/virtual/2026/79272). Jul 2026.
- Fonseca Rivera, Africa. [Steering Awareness](https://arxiv.org/abs/2511.21399). Nov 2025.
- Anthropic. [Natural Language Autoencoders](https://transformer-circuits.pub/2026/nla/). May 2026.
- Karvonen et al. [Activation Oracles](https://arxiv.org/abs/2512.15674). Dec 2025.
