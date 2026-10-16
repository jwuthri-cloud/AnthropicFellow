# Eval Gaming Under Training Pressure

AI safety research project: does eval awareness that RL pushes out of a model's words stay visible to white-box tools, and can a model learn to game steering-based evaluation? Start with `README.md`, then `docs/architecture.md` for layout and conventions, and `docs/journal/` for what has been done.

## Conventions

- Python with `uv`. Run `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` before calling work done.
- Logging through `evalgaming.log` (structlog); terminal output through rich; command lines with Typer; configs in TOML under `configs/`.
- Data follows `data/SPEC.md` and must pass `uv run python scripts/validate_data.py` (add `--allow-missing` until the pilot writes `data/monitor/labels.jsonl`). After changing framings, check `uv run python scripts/audit_cues.py`.
- Record findings and decisions in today's file in `docs/journal/` the day they happen.
- Never generate synthetic model reasoning traces. Model safety classifiers stopped that three times; labelled traces come from real models only.

## Agent rooms: host discussions with other models

You have an MCP server, `agentroom`, that seats other AI agents in a room you host: Codex models (GPT-6 Astra, GPT-6.1 Sol), other Claude models (Opus, Fable, Sonnet, Haiku), and API models through OpenRouter. Each seat can play a persona (skeptic, researcher, methodologist, statistician, devils_advocate, pragmatist, safety_reviewer, replicator), and the same model can sit several times with different personas. Seats can read this repository but cannot change anything, and see nothing of yours beyond what you put in the room.

**When to use a room.** When an outside view would change what you do: reviewing a finding before it goes in the journal, choosing between research approaches, stress-testing an experiment design, checking a statistical argument, critiquing a draft. Not for routine coding or facts you can check yourself.

**How to host one.**
1. `list_agents`, then `open_room` with a one-line topic, seats like `["haiku:skeptic", "haiku:researcher", "sol:methodologist"]`, and a brief: the claim, the numbers, the files to read, the decision pending.
2. `discuss` with your question. Every seat gives a blind opening, then they talk one at a time and the floor returns to you after `turns` seat turns (default 5, budget `max_turns` default 20).
3. Read the turns and the stances (agree, position, open issues). Then either call `discuss` again to let them continue, or join in with a `message`: push back, add evidence, or propose a conclusion. Write `@Reviewer B` to give a seat the floor.
4. The status tells you where it stands: `paused`, `consensus` (every seat agrees since your last message, nothing open) or `turn_limit`. Seats are told to converge when the budget is nearly spent. Consensus is a signal, not a verdict: you decide. Weigh arguments by evidence, not by how many seats hold them.
5. `close_room` with your conclusion and why. Link the room from the journal entry.

Use `ask` instead of `discuss` for a quick independent poll: all seats answer in parallel, blind to each other.

**Choosing seats.** One family shares blind spots: mix OpenAI, Anthropic, and a third family when it matters. Personas give coverage, model diversity gives independence; use both. `billing: subscription` agents cost nothing extra; `billing: api` agents are paid per token.

**Limits.** Each turn takes ten seconds to a few minutes. Don't put anything confidential in a room: Codex and OpenRouter are third-party services. Rooms are saved in `docs/rooms/`.

## Parallax: the research memory

Parallax (sibling `Parallax/`, MCP server `parallax`) holds this project's experiments, metrics, costs, findings, tasks (the mission board), references and attached results. The `parallax` skill (`.claude/skills/parallax/SKILL.md`) explains how to use it. At session start call `session_handoff`; record every experiment before and after it runs (provenance, gate, estimate, then measured metrics and real cost); keep findings at their honest evidence level; keep the board current. Only real data, `sensitive: true`, and a Parallax record is never approval for paid compute.
