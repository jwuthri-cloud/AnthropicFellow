"""Operations on rooms, shared by the MCP server and the CLI.

Two ways to talk to a room:
- :meth:`Hub.ask`: a panel round. Every seat answers the host in parallel, blind to the
  others' answers in that round.
- :meth:`Hub.discuss`: a conversation the host chairs. Blind opening statements, then one
  speaker at a time. Each call runs a few turns and pauses so the host can join in; the
  host alone decides when the discussion is over (:meth:`Hub.close_room`).
"""

from __future__ import annotations

import asyncio
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from agentroom.agents import Agent, AgentError, ClaudeCodeAgent, CodexAgent, DeepAgent
from agentroom.room import (
    HOST,
    STANCE_INSTRUCTION,
    Message,
    Room,
    RoomStore,
    Seat,
    Visibility,
    now,
    parse_stance,
)

log = structlog.get_logger(__name__)

KINDS: dict[str, type] = {"claude": ClaudeCodeAgent, "codex": CodexAgent, "deepagent": DeepAgent}

ANSWER = "Reply to the host's latest message above."
OPENING = (
    "Give your independent opening take on the host's question. "
    "You have not seen anyone else's view yet." + STANCE_INSTRUCTION
)
TURN = (
    "It is your turn in the discussion. Build on, challenge or concede specific points "
    "made by the others." + STANCE_INSTRUCTION
)
WRAP_UP = (
    "The discussion is close to its turn limit ({left} seat turns left). Converge now: say "
    "what you can agree to, what remains disputed and why, and propose exact wording for "
    "the conclusion."
)
MENTION = re.compile(r"@(Reviewer [A-Z])\b")
DEFAULT_MAX_TURNS = 20

OnReply = Callable[[Message], None]


def load_roster(path: Path) -> dict[str, Agent]:
    """Build every agent listed in a roster TOML file (see ``configs/agents.toml``)."""
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    workdir = (path.parent / config.get("workdir", ".")).resolve()
    roster: dict[str, Agent] = {}
    for name, spec in config["agents"].items():
        options = dict(spec)
        kind = options.pop("kind")
        if kind not in KINDS:
            raise ValueError(
                f"agent {name!r}: unknown kind {kind!r}, expected one of {list(KINDS)}"
            )
        roster[name] = KINDS[kind](name=name, workdir=workdir, **options)
    return roster


def load_personas(path: Path) -> dict[str, str]:
    """Read persona roles from a TOML file; an absent file means no personas."""
    if not path.exists():
        return {}
    return {name: spec["role"] for name, spec in tomllib.loads(path.read_text("utf-8")).items()}


@dataclass(frozen=True)
class Outcome:
    """Where a discussion stands after one call to :meth:`Hub.discuss`."""

    room_id: str
    status: str  # "paused", "consensus" or "turn_limit"; the host decides what happens next
    turns: list[Message]
    positions: dict[str, dict | None]
    turns_used: int
    max_turns: int


def has_consensus(room: Room) -> bool:
    """True when every seat has spoken since the host's last message, agreeing with nothing open."""
    messages = room.discussion
    last_host = max((i for i, m in enumerate(messages) if m.author == HOST), default=-1)
    latest = {m.author: m.stance for m in messages[last_host + 1 :] if not m.error}
    return all(
        (stance := latest.get(seat)) is not None and stance["agree"] and not stance["open"]
        for seat in room.members
    )


def latest_positions(room: Room) -> dict[str, dict | None]:
    """Each seat's most recent stance in the current discussion."""
    positions: dict[str, dict | None] = dict.fromkeys(room.members)
    positions |= {m.author: m.stance for m in room.discussion if m.author != HOST and not m.error}
    return positions


def next_speaker(room: Room) -> str:
    """Overdue seats first, then whoever the latest message names (@Reviewer X), then in order."""
    seats = room.members
    turns = [m for m in room.discussion if m.author != HOST]
    last = turns[-1].author if turns else None
    silence = dict.fromkeys(seats, len(turns))
    for age, message in enumerate(reversed(turns)):
        silence[message.author] = min(silence[message.author], age)
    overdue = [s for s in seats if s != last and silence[s] >= len(seats)]
    if overdue:
        return max(overdue, key=lambda s: silence[s])
    if room.discussion:
        latest = room.discussion[-1]
        labels = {room.seat(s).label: s for s in seats}
        for label in MENTION.findall(latest.text):
            if labels.get(label) not in (None, latest.author):
                return labels[label]
    index = seats.index(last) if last in seats else -1
    return seats[(index + 1) % len(seats)]


@dataclass(frozen=True)
class Hub:
    """The roster of available agents, their personas, and the rooms they meet in."""

    roster: dict[str, Agent]
    store: RoomStore
    workdir: Path
    personas: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_files(cls, roster_path: Path, rooms_dir: Path) -> Hub:
        """Hub from a roster file (personas.toml next to it) and a directory for rooms."""
        roster = load_roster(roster_path)
        workdir = next(iter(roster.values())).workdir if roster else Path.cwd()
        personas = load_personas(roster_path.parent / "personas.toml")
        return cls(roster, RoomStore(rooms_dir), workdir, personas)

    def make_seats(self, members: list[str], roles: dict[str, str] | None = None) -> list[Seat]:
        """Turn specs like ``haiku:skeptic`` into seats with unique names and labels."""
        if not members:
            raise ValueError("a room needs at least one seat")
        roles = roles or {}
        seats, taken = [], Counter()
        for index, spec in enumerate(members):
            agent_name, _, persona = spec.partition(":")
            if agent_name not in self.roster:
                raise KeyError(f"unknown agent {agent_name!r}; available: {sorted(self.roster)}")
            if persona and persona not in self.personas:
                raise KeyError(f"unknown persona {persona!r}; available: {sorted(self.personas)}")
            base = f"{agent_name}-{persona}" if persona else agent_name
            taken[base] += 1
            name = base if taken[base] == 1 else f"{base}-{taken[base]}"
            agent = self.roster[agent_name]
            role = roles.get(name) or self.personas.get(persona, "")
            seats.append(
                Seat(
                    name=name,
                    label=f"Reviewer {chr(ord('A') + index)}",
                    agent=agent_name,
                    model=agent.model,
                    family=agent.family,
                    billing=agent.billing,
                    persona=persona,
                    role=role,
                )
            )
        return seats

    def open_room(
        self, topic: str, members: list[str], brief: str = "", roles: dict[str, str] | None = None
    ) -> Room:
        """Seat ``members`` (``agent`` or ``agent:persona``, in order) and save the empty room."""
        seats = self.make_seats(members, roles)
        room = Room(self.store.new_id(topic), topic, brief, seats, str(self.workdir))
        self.store.save(room)
        log.info("room.opened", room=room.id, seats=room.members)
        return room

    async def _turn(
        self, room: Room, seat: str, instruction: str, visibility: Visibility, discussion: bool
    ) -> Message:
        """One seat speaks; failures become recorded messages instead of exceptions."""
        prompt = room.prompt(seat, instruction, visibility)
        agent = self.roster[room.seat(seat).agent]
        round_number = room.round
        try:
            reply = await agent.respond(room.system_prompt(seat, discussion), prompt)
        except (AgentError, OSError) as error:
            log.warning("turn.failed", room=room.id, seat=seat, error=str(error))
            return Message(round_number, seat, f"[failed: {error}]", now(), error=True)
        text, stance = parse_stance(reply.text) if discussion else (reply.text, None)
        log.info("turn.done", room=room.id, seat=seat, seconds=round(reply.seconds, 1))
        return Message(
            round_number, seat, text, now(), reply.seconds, reply.cost_usd, stance=stance
        )

    async def ask(
        self,
        room_id: str,
        question: str,
        to: list[str] | None = None,
        visibility: Visibility = "none",
        on_reply: OnReply | None = None,
    ) -> list[Message]:
        """Panel round: seats answer the host in parallel, blind to each other's answers.

        ``visibility`` controls which earlier rounds each seat reads. ``on_reply`` is called
        with each answer as soon as it arrives.
        """
        room = self.store.load(room_id)
        targets = to or room.members
        for name in targets:
            room.seat(name)
        room.messages.append(Message(room.round + 1, HOST, question, now()))
        log.info("round.started", room=room_id, round=room.round, to=targets)

        async def answer(seat: str) -> Message:
            message = await self._turn(room, seat, ANSWER, visibility, discussion=False)
            if on_reply:
                on_reply(message)
            return message

        replies = list(await asyncio.gather(*(answer(seat) for seat in targets)))
        room.messages.extend(replies)
        self.store.save(room)
        return replies

    async def discuss(
        self,
        room_id: str,
        message: str = "",
        turns: int = 5,
        max_turns: int | None = None,
        visibility: Visibility = "all",
        blind_opening: bool = True,
        stop_on_agreement: bool = True,
        on_reply: OnReply | None = None,
    ) -> Outcome:
        """Run up to ``turns`` seat turns of a discussion the host chairs, then pause.

        The first call starts the discussion: ``message`` is the question, every seat gives
        a blind opening statement (one parallel step), and ``max_turns`` (default 20) sets the
        seat-turn budget. Later calls continue it: ``message``, if given, is the host joining
        in, and naming a seat as ``@Reviewer B`` gives it the floor. Raising ``max_turns``
        extends the budget.

        Pauses early when every seat has spoken since the host's last message and agrees with
        nothing open ("consensus", unless ``stop_on_agreement`` is false), or when the budget
        is spent ("turn_limit"). Within one
        round of the limit, seats are told to converge on a conclusion. Nothing ends the
        discussion except :meth:`close_room`: the host decides.
        """
        room = self.store.load(room_id)
        if len(room.seats) < 2:
            raise ValueError("a discussion needs at least two seats; use ask for one")
        starting = room.discussion_start is None
        if starting:
            if not message:
                raise ValueError("starting a discussion needs the host's question")
            room.discussion_start = len(room.messages)
        room.max_turns = max_turns or room.max_turns or DEFAULT_MAX_TURNS
        if message:
            room.messages.append(Message(room.round + 1, HOST, message, now()))
        self.store.save(room)
        log.info("discussion.step", room=room_id, used=room.turns_used, budget=room.max_turns)
        new: list[Message] = []

        async def speak(seat: str, instruction: str, seen: Visibility) -> Message:
            reply = await self._turn(room, seat, instruction, seen, discussion=True)
            if on_reply:
                on_reply(reply)
            return reply

        def record(reply: Message) -> None:
            room.messages.append(reply)
            new.append(reply)
            self.store.save(room)

        if starting and blind_opening:
            # Recorded only after all openers have spoken, so no opening sees another.
            openers = room.members[: room.max_turns]
            for reply in await asyncio.gather(*(speak(s, OPENING, "none") for s in openers)):
                record(reply)
        while (
            len(new) < turns
            and room.turns_used < room.max_turns
            and not (stop_on_agreement and new and has_consensus(room))
        ):
            left = room.max_turns - room.turns_used
            if room.turns_used == 0:
                instruction = OPENING
            elif left <= len(room.seats):
                instruction = WRAP_UP.format(left=left) + STANCE_INSTRUCTION
            else:
                instruction = TURN
            record(await speak(next_speaker(room), instruction, visibility))

        if has_consensus(room):
            status = "consensus"
        elif room.turns_used >= room.max_turns:
            status = "turn_limit"
        else:
            status = "paused"
        log.info("discussion.paused", room=room_id, status=status, used=room.turns_used)
        return Outcome(
            room_id, status, new, latest_positions(room), room.turns_used, room.max_turns
        )

    def close_room(self, room_id: str, conclusion: str) -> Path:
        """Record the host's conclusion and return the transcript path."""
        room = self.store.load(room_id)
        room.conclusion = conclusion
        log.info("room.closed", room=room_id)
        return self.store.save(room)
