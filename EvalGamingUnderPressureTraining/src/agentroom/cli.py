"""``agentroom`` command line: the same rooms the main agent uses, with you as the host."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, TypeVar

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agentroom.hub import Hub, OnReply, Outcome
from agentroom.room import Message, describe_stance
from agentroom.server import main as serve_mcp
from evalgaming.log import configure

app = typer.Typer(help="Host discussions with other AI agents in rooms.", no_args_is_help=True)
console = Console()
T = TypeVar("T")

RosterOption = Annotated[Path, typer.Option(help="Roster TOML file.")]
RoomsOption = Annotated[Path, typer.Option(help="Where rooms are saved.")]
DEFAULT_ROSTER = Path("configs/agents.toml")
DEFAULT_ROOMS = Path("docs/rooms")
STATUS_TEXT = {
    "paused": "Paused.",
    "consensus": "[green]Every seat agrees, with nothing open.[/]",
    "turn_limit": "[yellow]Turn limit reached.[/]",
}


def _hub(roster: Path, rooms: Path) -> Hub:
    configure("WARNING")
    return Hub.from_files(roster, rooms)


def _print_turn(message: Message, label: str) -> None:
    timing = f" · {message.seconds:.0f}s" if message.seconds else ""
    stance = f"stance: {describe_stance(message.stance)}" if message.stance else None
    console.print(
        Panel(
            Markdown(message.text),
            title=f"{message.author} · {label}{timing}",
            subtitle=stance,
            border_style="red" if message.error else "cyan",
        )
    )


def _live(hub: Hub, room_id: str, pending: list[str], run: Callable[[OnReply], Awaitable[T]]) -> T:
    """Run ``run(on_reply)`` under a status line, printing each turn as it arrives."""
    pending = list(pending)
    room = hub.store.load(room_id)

    def waiting() -> str:
        who = ", ".join(pending) if pending else "the next speaker"
        return f"Waiting for {who} (usually 30s to a few minutes per turn)"

    with console.status(waiting()) as status:

        def on_reply(message: Message) -> None:
            if message.author in pending:
                pending.remove(message.author)
            _print_turn(message, room.display(message.author))
            status.update(waiting())

        return asyncio.run(run(on_reply))


def _print_positions(outcome: Outcome) -> None:
    table = Table("Seat", "Stance", title=f"Turns {outcome.turns_used} of {outcome.max_turns}")
    for seat, stance in outcome.positions.items():
        table.add_row(seat, describe_stance(stance))
    console.print(table)
    console.print(STATUS_TEXT[outcome.status])


def _host_choice(outcome: Outcome, step: int) -> str:
    """Show the host's options as a legend and return the one picked."""
    grow = f"add {step} turns to the budget ({outcome.max_turns} → {outcome.max_turns + step})"
    at_limit = outcome.status == "turn_limit"
    default = "c" if outcome.status == "paused" else "x"
    options = [
        ("c", "continue", f"{grow}, let the seats talk" if at_limit else f"seats talk {step} more"),
        ("s", "say", "post your message to the room; @Reviewer B gives B the floor next"),
        ("e", "extend", f"{grow}, then continue"),
        ("x", "conclude", "write your conclusion and close the room"),
    ]
    legend = Table.grid(padding=(0, 2))
    for key, name, what in options:
        mark = "  [dim]← Enter[/]" if key == default else ""
        legend.add_row(f"[bold cyan]{key}[/]", f"[bold]{name}[/]", f"{what}{mark}")
    console.print(legend)
    return Prompt.ask("Your move", choices=[key for key, _, _ in options], default=default)


@app.command()
def agents(roster: RosterOption = DEFAULT_ROSTER, rooms: RoomsOption = DEFAULT_ROOMS) -> None:
    """List the agents and personas you can seat."""
    hub = _hub(roster, rooms)
    table = Table("Agent", "Model", "Family", "Billing", title="Agents")
    for agent in hub.roster.values():
        table.add_row(agent.name, agent.model, agent.family, agent.billing)
    console.print(table)
    personas = Table("Persona", "Role", title="Personas (seat as agent:persona)")
    for name, role in hub.personas.items():
        personas.add_row(name, role)
    console.print(personas)


@app.command()
def ask(
    question: str,
    members: Annotated[str, typer.Option(help="Comma-separated seats, agent or agent:persona.")],
    topic: Annotated[str, typer.Option(help="What the room is for.")] = "",
    brief_file: Annotated[Path | None, typer.Option(help="Brief every seat sees.")] = None,
    roster: RosterOption = DEFAULT_ROSTER,
    rooms: RoomsOption = DEFAULT_ROOMS,
) -> None:
    """Panel round: every seat answers the same question independently, in parallel."""
    hub = _hub(roster, rooms)
    brief = brief_file.read_text(encoding="utf-8") if brief_file else ""
    room = hub.open_room(topic or question[:80], members.split(","), brief)
    console.print(f"Room [bold]{room.id}[/]")
    _live(
        hub, room.id, room.members, lambda on_reply: hub.ask(room.id, question, on_reply=on_reply)
    )
    console.print(f"[dim]Transcript: {hub.store.root / room.id / 'transcript.md'}[/]")


@app.command()
def discuss(
    question: Annotated[str, typer.Argument(help="The question; omit when resuming.")] = "",
    members: Annotated[str, typer.Option(help="Comma-separated seats, agent:persona.")] = "",
    room: Annotated[str | None, typer.Option(help="Resume this room instead.")] = None,
    topic: Annotated[str, typer.Option(help="What the room is for.")] = "",
    brief_file: Annotated[Path | None, typer.Option(help="Brief every seat sees.")] = None,
    max_turns: Annotated[int, typer.Option(help="Seat-turn budget.")] = 20,
    step: Annotated[int, typer.Option(help="Seat turns between your check-ins.")] = 5,
    roster: RosterOption = DEFAULT_ROSTER,
    rooms: RoomsOption = DEFAULT_ROOMS,
) -> None:
    """Host a conversation: seats talk turn by turn, you check in, join in, and conclude."""
    hub = _hub(roster, rooms)
    if room is None:
        if not (question and members):
            raise typer.BadParameter("a new discussion needs a question and --members")
        brief = brief_file.read_text(encoding="utf-8") if brief_file else ""
        room = hub.open_room(topic or question[:80], members.split(","), brief).id
        console.print(f"Room [bold]{room}[/]")
        pending = hub.store.load(room).members
    else:
        pending = []
    room_id, message, budget = room, question, max_turns

    while True:
        outcome = _live(
            hub,
            room_id,
            pending,
            lambda on_reply, text=message, limit=budget: hub.discuss(
                room_id, text, turns=step, max_turns=limit, on_reply=on_reply
            ),
        )
        _print_positions(outcome)
        pending, message = [], ""
        choice = _host_choice(outcome, step)
        if choice == "x":
            path = hub.close_room(room_id, Prompt.ask("Your conclusion"))
            console.print(f"[dim]Closed. Transcript: {path}[/]")
            return
        if choice == "s":
            message = Prompt.ask("Your message (write @Reviewer B to give someone the floor)")
        if choice == "e" or outcome.status == "turn_limit":
            budget = outcome.max_turns + step


@app.command()
def show(room_id: str, rooms: RoomsOption = DEFAULT_ROOMS) -> None:
    """Print a room's transcript."""
    transcript = rooms / room_id / "transcript.md"
    console.print(Markdown(transcript.read_text(encoding="utf-8")))


@app.command()
def serve() -> None:
    """Run the MCP server over stdio (Claude Code starts this itself via .mcp.json)."""
    serve_mcp()
