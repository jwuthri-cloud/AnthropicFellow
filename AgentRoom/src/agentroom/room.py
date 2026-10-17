"""A room: who sits in it, what each seat may see, and the record of what was said.

Pure data and text building, no I/O except :class:`RoomStore`, so the visibility and
conversation rules are easy to test.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

HOST = "host"

# How much of the discussion each seat sees when it speaks:
#   "none": only the host's messages and its own earlier turns (independent reviews)
#   "all":  every seat's turns (open discussion)
#   "ring": its own and the previous seat's turns (sparse discussion)
#   {seat: [seats]}: an explicit graph of who reads whom
Visibility = str | Mapping[str, list[str]]

RULES = """\
You are {label}, one of {count} participants in a research discussion room. \
The host is the lead researcher's agent: it sets the questions and makes the decisions.{role}

Rules:
- Think independently. Agree only when convinced, and say plainly when you disagree, \
including with the host.
- Ground every claim: cite repository files as path:line, papers by title and year, \
numbers with their sample size.
- Say what result or evidence would change your mind.
- Other participants appear under anonymous labels with their role. Judge the argument, \
not the author.
- You may read the research repository at {workdir}, read-only. You cannot change anything."""

ANSWER_RULES = "\n- Answer in markdown, in at most about 800 words unless the host asks otherwise."

DISCUSSION_RULES = """
- This is a live discussion, one speaker at a time. Keep each turn under 200 words.
- Respond to specific points and name whom you answer, e.g. "Reviewer B is right that...".
- To hand the floor to someone, write @Reviewer B.
- Concede points when convinced. Never repeat an argument already made.
- If you have nothing new to add, say so in one line.
- Write only your own turn. Don't start it with a speaker label such as "Host:" or your own label.
- The host may join in. When the host addresses you, answer the host first.
- The host, not the group, decides when the discussion is over."""

STANCE_INSTRUCTION = """
End your turn with one line in exactly this form:
STANCE: {"agree": true, "position": "your position in one sentence", "open": []}
"agree" is true only if you would sign the group's emerging conclusion as it stands. \
"open" lists the issues you still consider unresolved."""

STANCE_LINE = re.compile(r"^\s*STANCE:\s*(\{.*\})\s*$", re.MULTILINE)


def now() -> str:
    """Current UTC time, ISO formatted to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_stance(text: str) -> tuple[str, dict | None]:
    """Split a turn into its prose and its stance; the stance is None if missing or malformed."""
    matches = list(STANCE_LINE.finditer(text))
    if not matches:
        return text.strip(), None
    last = matches[-1]
    prose = (text[: last.start()] + text[last.end() :]).strip()
    try:
        stance = json.loads(last.group(1))
    except json.JSONDecodeError:
        return prose, None
    if not isinstance(stance, dict) or not isinstance(stance.get("agree"), bool):
        return prose, None
    open_issues = stance.get("open") or []
    return prose, {
        "agree": stance["agree"],
        "position": str(stance.get("position", "")),
        "open": [str(issue) for issue in open_issues] if isinstance(open_issues, list) else [],
    }


def describe_stance(stance: dict | None) -> str:
    """One-line summary of a stance for transcripts and peers."""
    if stance is None:
        return "no stance given"
    verdict = "agrees" if stance["agree"] and not stance["open"] else "not yet agreed"
    open_part = f"; open: {'; '.join(stance['open'])}" if stance["open"] else ""
    return f"{verdict}: {stance['position']}{open_part}"


@dataclass(frozen=True)
class Seat:
    """One seat in a room: an agent from the roster, optionally playing a persona."""

    name: str
    label: str
    agent: str
    model: str
    family: str
    billing: str
    persona: str = ""
    role: str = ""


@dataclass(frozen=True)
class Message:
    """One entry in the room's record."""

    round: int
    author: str
    text: str
    at: str
    seconds: float | None = None
    cost_usd: float | None = None
    error: bool = False
    stance: dict | None = None


@dataclass
class Room:
    """A discussion between the host and a set of seats."""

    id: str
    topic: str
    brief: str
    seats: list[Seat]
    workdir: str
    created: str = field(default_factory=now)
    messages: list[Message] = field(default_factory=list)
    conclusion: str = ""
    discussion_start: int | None = None
    max_turns: int | None = None

    @property
    def members(self) -> list[str]:
        """Seat names in seating order."""
        return [seat.name for seat in self.seats]

    @property
    def round(self) -> int:
        """Number of the latest round, 0 before the first host message."""
        return max((m.round for m in self.messages), default=0)

    @property
    def discussion(self) -> list[Message]:
        """Messages since the current discussion started (host and seats), or none."""
        return [] if self.discussion_start is None else self.messages[self.discussion_start :]

    @property
    def turns_used(self) -> int:
        """Seat turns taken in the current discussion."""
        return sum(1 for m in self.discussion if m.author != HOST)

    def seat(self, name: str) -> Seat:
        """Look up a seat by name."""
        for seat in self.seats:
            if seat.name == name:
                return seat
        raise KeyError(f"{name!r} is not in room {self.id}; seats: {self.members}")

    def display(self, name: str) -> str:
        """How other seats see ``name``: its anonymous label plus its persona."""
        seat = self.seat(name)
        return f"{seat.label} ({seat.persona})" if seat.persona else seat.label

    def peers(self, member: str, visibility: Visibility) -> set[str]:
        """Seats whose turns ``member`` may read under ``visibility``."""
        if isinstance(visibility, Mapping):
            unknown = set(visibility.get(member, [])) - set(self.members)
            if unknown:
                raise KeyError(f"unknown seats in visibility graph: {sorted(unknown)}")
            return set(visibility.get(member, [])) - {member}
        if visibility == "none":
            return set()
        if visibility == "all":
            return set(self.members) - {member}
        if visibility == "ring":
            index = self.members.index(member)
            return {self.members[index - 1]} - {member}
        raise ValueError(f"visibility must be none, all, ring or a mapping, got {visibility!r}")

    def system_prompt(self, member: str, discussion: bool = False) -> str:
        """Room rules for one seat, with its role and the rules of the current mode."""
        seat = self.seat(member)
        role = f"\n\nYour role in this room: {seat.role}" if seat.role else ""
        rules = RULES.format(
            label=seat.label, count=len(self.seats), role=role, workdir=self.workdir
        )
        return rules + (DISCUSSION_RULES if discussion else ANSWER_RULES)

    def prompt(self, member: str, instruction: str, visibility: Visibility) -> str:
        """Everything ``member`` may see, then what it should do now."""
        peers = self.peers(member, visibility)
        parts = [f"# Topic\n{self.topic}"]
        if self.brief:
            parts.append(f"# Brief\n{self.brief}")
        history = []
        for message in self.messages:
            if message.error:
                continue
            if message.author == HOST:
                header = "Host"
            elif message.author == member:
                header = "You"
            elif message.author in peers:
                header = self.display(message.author)
            else:
                continue
            entry = f"## Round {message.round}, {header}\n{message.text}"
            if message.stance is not None and message.author != HOST:
                entry += f"\n\n(Stance: {describe_stance(message.stance)})"
            history.append(entry)
        if history:
            parts.append("# Discussion so far\n\n" + "\n\n".join(history))
        parts.append(f"# Your turn\n{instruction}")
        return "\n\n".join(parts)

    def to_markdown(self) -> str:
        """Human-readable record of the room, with real model names."""
        lines = [
            f"# {self.topic}",
            "",
            f"Room `{self.id}`, opened {self.created}.",
            "",
            "| Seat | Label | Persona | Agent | Model | Family | Billing |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {s.name} | {s.label} | {s.persona} | {s.agent} | {s.model} | {s.family} | "
            f"{s.billing} |"
            for s in self.seats
        ]
        if self.brief:
            lines += ["", "## Brief", "", self.brief]
        for message in self.messages:
            if message.author == HOST:
                lines += ["", f"## Round {message.round}: host", "", message.text]
                continue
            seat = self.seat(message.author)
            timing = f", {message.seconds:.0f}s" if message.seconds is not None else ""
            status = ", failed" if message.error else ""
            persona = f", {seat.persona}" if seat.persona else ""
            lines += ["", f"### {seat.name} ({seat.label}{persona}, {seat.model}{timing}{status})"]
            lines += ["", message.text]
            if message.stance is not None:
                lines += ["", f"> Stance: {describe_stance(message.stance)}"]
        if self.conclusion:
            lines += ["", "## Conclusion", "", self.conclusion]
        return "\n".join(lines) + "\n"


def slugify(text: str, limit: int = 40) -> str:
    """Lowercase, dash-separated, filesystem-safe version of ``text``."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].rstrip("-")


class RoomStore:
    """Saves each room as ``<root>/<id>/room.json`` plus a readable ``transcript.md``."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def new_id(self, topic: str) -> str:
        """Date-stamped id that sorts chronologically and says what the room is about."""
        stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M%S")
        return f"{stamp}-{slugify(topic)}"

    def save(self, room: Room) -> Path:
        """Write the room and its transcript; return the transcript path."""
        folder = self.root / room.id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "room.json").write_text(json.dumps(asdict(room), indent=2), encoding="utf-8")
        transcript = folder / "transcript.md"
        transcript.write_text(room.to_markdown(), encoding="utf-8")
        return transcript

    def load(self, room_id: str) -> Room:
        """Read a saved room."""
        data = json.loads((self.root / room_id / "room.json").read_text(encoding="utf-8"))
        # Rooms saved before personas existed have no "agent" field: the seat was the agent.
        data["seats"] = [Seat(**({"agent": seat["name"]} | seat)) for seat in data["seats"]]
        data["messages"] = [Message(**message) for message in data["messages"]]
        return Room(**data)

    def list(self) -> list[str]:
        """Ids of saved rooms, oldest first."""
        if not self.root.exists():
            return []
        return sorted(p.parent.name for p in self.root.glob("*/room.json"))
