"""MCP server that lets the main Claude Code session host rooms of other agents.

Registered for this project in ``.mcp.json``. Paths come from the environment so the same
server works from any checkout: ``AGENTROOM_ROSTER`` (default ``configs/agents.toml``,
with ``personas.toml`` next to it) and ``AGENTROOM_DIR`` (default ``docs/rooms``).
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from agentroom.hub import Hub
from agentroom.room import Message
from evalgaming.log import configure

INSTRUCTIONS = """\
Agent rooms let you host discussions with other AI agents: Codex models (OpenAI), other
Claude models, and API models through OpenRouter, each optionally playing a persona such
as skeptic or statistician. You are the host: you set the question, join in, and decide
when the discussion has reached a conclusion. Call list_agents first."""

mcp = MCPServer("agentroom", instructions=INSTRUCTIONS)
_hub: Hub | None = None


def hub() -> Hub:
    """The hub, built on first use so the server starts even if the roster is broken."""
    global _hub
    if _hub is None:
        _hub = Hub.from_files(
            Path(os.environ.get("AGENTROOM_ROSTER", "configs/agents.toml")),
            Path(os.environ.get("AGENTROOM_DIR", "docs/rooms")),
        )
    return _hub


def _turn(message: Message) -> dict:
    return {
        "seat": message.author,
        "text": message.text,
        "stance": message.stance,
        "seconds": message.seconds,
        "failed": message.error,
    }


@mcp.tool()
def list_agents() -> dict:
    """List the agents you can seat and the personas they can play.

    billing "subscription" agents cost nothing extra per call; "api" agents are paid per
    token, so seat them only when their model family adds a view the others lack.
    """
    return {
        "agents": [
            {"name": a.name, "model": a.model, "family": a.family, "billing": a.billing}
            for a in hub().roster.values()
        ],
        "personas": hub().personas,
    }


@mcp.tool()
def open_room(
    topic: str, members: list[str], brief: str = "", roles: dict[str, str] | None = None
) -> dict:
    """Open a room and seat agents in it. Returns the room id and the seats.

    topic: one line saying what the room is for.
    members: seats as "agent" or "agent:persona", e.g. ["haiku:skeptic", "haiku:researcher",
        "sol:methodologist"]. The same agent can sit several times with different personas.
        Mix model families for independent views; one family shares blind spots.
    brief: shared context every seat sees on every turn: the claim, the evidence, file paths
        to read, the decision pending. Seats can read the repository but nothing else of yours.
    roles: optional {seat name: custom role text}, overriding the persona's role.
    """
    room = hub().open_room(topic, members, brief, roles)
    return {"room_id": room.id, "seats": [asdict(seat) for seat in room.seats]}


@mcp.tool()
async def ask(
    room_id: str,
    message: str,
    to: list[str] | None = None,
    visibility: str = "none",
    graph: dict[str, list[str]] | None = None,
) -> dict:
    """Panel round: seats answer you in parallel, blind to each other's answers this round.

    Use for independent reviews or a quick poll. For a back-and-forth, use discuss.
    to: which seats answer (default all). visibility: which earlier rounds each seat reads,
    "none", "all" or "ring"; graph {seat: [seats it reads]} overrides it.
    """
    replies = await hub().ask(room_id, message, to, graph or visibility)
    return {"replies": [_turn(r) for r in replies]}


@mcp.tool()
async def discuss(
    room_id: str,
    message: str = "",
    turns: int = 5,
    max_turns: int | None = None,
    visibility: str = "all",
    stop_on_agreement: bool = True,
) -> dict:
    """Chair a conversation: seats talk one at a time, then the floor returns to you.

    First call: message is your question. Every seat gives a blind opening statement, then
    the conversation runs. max_turns (default 20) is the seat-turn budget.
    Later calls: message (optional) is you joining in, e.g. pushing back or proposing a
    conclusion. Write "@Reviewer B" to give that seat the floor. Raise max_turns to extend.

    Runs up to `turns` seat turns, then pauses with a status:
      "paused"     - step done; read it and continue, join in, or close.
      "consensus"  - every seat has spoken since your last message and agrees, nothing open.
                     Confirm with close_room, or push further.
      "turn_limit" - budget spent. Close, or raise max_turns.
    Within one round of the limit, seats are told to converge on conclusion wording.
    Every turn carries a stance: agree, position, open issues. You decide when it is over.
    stop_on_agreement=false keeps the conversation going through agreement.
    """
    outcome = await hub().discuss(
        room_id,
        message,
        turns=turns,
        max_turns=max_turns,
        visibility=visibility,
        stop_on_agreement=stop_on_agreement,
    )
    return {
        "status": outcome.status,
        "turns_used": outcome.turns_used,
        "max_turns": outcome.max_turns,
        "positions": outcome.positions,
        "new_turns": [_turn(t) for t in outcome.turns],
    }


@mcp.tool()
def read_room(room_id: str) -> str:
    """Return the full transcript of a room as markdown, with real model names."""
    return hub().store.load(room_id).to_markdown()


@mcp.tool()
def list_rooms() -> list[str]:
    """Ids of all saved rooms, oldest first."""
    return hub().store.list()


@mcp.tool()
def close_room(room_id: str, conclusion: str) -> str:
    """End the room with your conclusion: what you decided and why. Returns the transcript path."""
    return str(hub().close_room(room_id, conclusion))


def main() -> None:
    """Run the server over stdio. Logs go to stderr so they never corrupt the protocol."""
    configure(os.environ.get("AGENTROOM_LOG_LEVEL", "INFO"))
    mcp.run()
