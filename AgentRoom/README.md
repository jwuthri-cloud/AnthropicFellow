# Agent rooms

A room seats several AI agents around one topic so the main agent (the Claude Code session working in a research repo) can get independent views and cross-examination before deciding something. Rooms are for findings, research approach, experiment design and drafts, not for routine coding.

AgentRoom is shared by the research projects in this folder. Each project keeps its own roster, personas and saved rooms; this project holds only the code.

## Set up a research project

1. Copy `examples/agents.toml` and `examples/personas.toml` into the project's `configs/`. `workdir` in `agents.toml` is the directory seats may read, relative to that file (`".."` = the project root).
2. Register the MCP server in the project's `.mcp.json`; `--project` runs AgentRoom's environment while the working directory stays the research project:

   ```json
   "agentroom": {
     "command": "uv",
     "args": ["run", "--project", "/Users/julien/Documents/Repos/AnthropicFellow/AgentRoom", "--extra", "openrouter", "agentroom-mcp"],
     "env": {"AGENTROOM_ROSTER": "configs/agents.toml", "AGENTROOM_DIR": "docs/rooms"}
   }
   ```

3. Raise the MCP tool timeout in the project's `.claude/settings.json` (rooms take minutes) and enable the server.

## Who can sit in a room

The roster is the project's `configs/agents.toml`. Three kinds of agent:

| Kind | How it runs | Billing | Family |
| --- | --- | --- | --- |
| `claude` | `claude -p` (Claude Code CLI) | your Claude subscription | anthropic |
| `codex` | `codex exec` (Codex CLI) | your ChatGPT subscription | openai |
| `deepagent` | a [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) harness on an API model, e.g. `openrouter:deepseek/...` | paid per token, needs `OPENROUTER_API_KEY` | the model maker |

Every agent can read the repository and nothing else. Claude seats get only the `Read`, `Glob` and `Grep` tools, run from an empty directory with no MCP servers or project settings, so they cannot open rooms themselves. Codex seats run in the `read-only` sandbox without your Codex config. Deep-agent seats see the repo mounted read-only at `/repo/`, with `.env` files and keys unreadable.

Add an agent by adding a `[agents.<name>]` table. Codex model ids are listed in `~/.codex/models_cache.json`.

## Seats and personas

A seat is an agent from the roster, optionally playing a persona from the project's `configs/personas.toml`: `haiku:skeptic`, `haiku:researcher`, `sol:methodologist`. The same agent can take several seats; seat names are made unique (`haiku-skeptic`, `haiku-skeptic-2`). A persona is a role paragraph added to the seat's system prompt; `roles={seat: text}` overrides it for one room. Add a persona by adding a table to `personas.toml`.

## Two ways to talk to a room

**`ask`, a panel round.** Every seat answers the host in parallel and never sees the other answers from the same round. Use it for independent reviews or a quick poll. `visibility` sets which earlier rounds each seat reads.

**`discuss`, a conversation the host chairs.**

```
host: discuss(question)            seats: blind openings, in parallel
                                   then one speaker at a time, each reading the whole thread
                                   every turn ends with a stance: agree, position, open issues
      <- pause after `turns` seat turns, on consensus, or at the turn limit
host: discuss(message="@Reviewer B, ...")   the host joins in; B gets the floor
      <- pause
host: close_room(conclusion)       only the host ends a discussion
```

- **Turn order.** A seat silent for a full cycle speaks first. Otherwise, a seat named as `@Reviewer X` in the latest message (by the host or another seat) gets the floor. Otherwise, the next seat in order.
- **Consensus pauses, the host decides.** The call pauses with status `consensus` when every seat has spoken since the host's last message and agrees with nothing open. It does not close the room: the host confirms with `close_room` or pushes further. `stop_on_agreement=false` keeps going through agreement.
- **Turn budget and wrap-up.** `max_turns` (default 20) counts seat turns, openings included. Within one round of the limit, seats are told to converge: state what they agree to, what remains disputed, and exact wording for the conclusion. At the limit the status is `turn_limit`; the host closes or raises `max_turns`.
- **Visibility (sparsity).** `all` by default; `ring` makes each seat read only the previous seat, which keeps views diverse longer; a graph `{seat: [seats]}` sets any topology. Openings are always blind.

## How turns are built

- **Stateless seats.** Each turn, the room builds the seat's full prompt: room rules, its role, the brief, the part of the thread it may see (with each speaker's latest stance), and its instruction. The transcript records exactly what every seat saw; no CLI session state is involved.
- **Anonymity.** Seats see each other as `Reviewer B (skeptic)`, never by model, so they judge arguments rather than brands. The host and the saved transcript show real names.
- **Records.** Every room is saved after each turn in `AGENTROOM_DIR/<id>/` (by convention the project's `docs/rooms/`) as `room.json` and `transcript.md`, so progress survives interruptions.

## Using rooms

From Claude Code, through the `agentroom` MCP server registered in the project's `.mcp.json`: `list_agents`, `open_room`, `ask`, `discuss`, `read_room`, `list_rooms`, `close_room`. The project's `CLAUDE.md` tells the main agent how to host.

From a terminal in the research project, where you are the host:

```bash
uv run --project ../AgentRoom --extra openrouter agentroom agents
```

```bash
uv run --project ../AgentRoom --extra openrouter agentroom discuss "Is the week-7 kill criterion well defined?" --members haiku:skeptic,haiku:researcher,sol:methodologist --max-turns 12 --step 4
```

After each step it shows every seat's stance and asks you to continue, say something (use `@Reviewer B`), extend the budget, or conclude. `agentroom discuss --room <id>` resumes a room; `agentroom ask` runs a panel round; `agentroom show <id>` prints a transcript.

## Code

| Module | Responsibility |
| --- | --- |
| `src/agentroom/agents.py` | The `Agent` interface and the three adapters |
| `src/agentroom/room.py` | Seats, messages, visibility rules, prompt building, markdown, storage |
| `src/agentroom/hub.py` | Roster and personas, seats, panel rounds, host-chaired discussions, turn order, consensus |
| `src/agentroom/server.py` | MCP server for the main agent |
| `src/agentroom/cli.py` | `agentroom` command line |

Tests in `tests/test_agentroom.py` cover seats and personas, blind rounds, anonymity, turn order and floor passing, consensus pauses, wrap-up, the turn budget, failures, storage, and the read-only flags passed to each CLI.

## Limits

- Subscription rate limits cap how many rooms can run at once.
- Codex and OpenRouter are third-party services: no confidential or mentor-shared material in rooms.
- Agreement between models is not evidence. Models trained on similar data can be wrong together; the host decides on the arguments.
