"""Tests for agent rooms: seats and personas, panel rounds, host-chaired discussions,
persistence, and the read-only CLI adapters."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentroom.agents import AgentError, ClaudeCodeAgent, CodexAgent, Reply
from agentroom.hub import Hub, load_personas, load_roster, next_speaker
from agentroom.room import RoomStore, parse_stance

REPO = Path(__file__).resolve().parents[1]
PERSONAS = {"skeptic": "Find confounds.", "researcher": "Push the idea forward."}


@dataclass
class FakeAgent:
    """Records what it is shown; answers with a fixed text, plus a stance when asked for one."""

    name: str
    model: str = "fake-1"
    family: str = "fake"
    billing: str = "subscription"
    agree: bool = False
    fail: bool = False
    prompts: list[str] = field(default_factory=list)
    systems: list[str] = field(default_factory=list)

    async def respond(self, system: str, prompt: str) -> Reply:
        self.prompts.append(prompt)
        self.systems.append(system)
        if self.fail:
            raise AgentError("boom")
        text = f"answer from {self.name}"
        if "STANCE:" in prompt:
            stance = {"agree": self.agree, "position": "p", "open": [] if self.agree else ["x"]}
            text += f"\nSTANCE: {json.dumps(stance)}"
        return Reply(text, seconds=1.0)


@pytest.fixture
def hub(tmp_path: Path) -> Hub:
    roster = {name: FakeAgent(name) for name in ("astra", "sonnet", "fable")}
    return Hub(roster, RoomStore(tmp_path), tmp_path, PERSONAS)


def run(coroutine):
    return asyncio.run(coroutine)


# Seats and personas


def test_same_agent_can_take_several_seats_with_personas(hub: Hub):
    room = hub.open_room("topic", ["astra:skeptic", "astra:researcher", "astra:skeptic"])
    assert room.members == ["astra-skeptic", "astra-researcher", "astra-skeptic-2"]
    assert room.seat("astra-skeptic").role == "Find confounds."
    assert room.display("astra-researcher") == "Reviewer B (researcher)"
    assert "Your role in this room: Find confounds." in room.system_prompt("astra-skeptic")


def test_seat_validation(hub: Hub):
    with pytest.raises(KeyError):
        hub.open_room("topic", ["gpt-99"])
    with pytest.raises(KeyError):
        hub.open_room("topic", ["astra:poet"])
    with pytest.raises(ValueError):
        hub.open_room("topic", [])


def test_custom_role_overrides_persona(hub: Hub):
    room = hub.open_room("topic", ["astra:skeptic"], roles={"astra-skeptic": "Only check stats."})
    assert room.seat("astra-skeptic").role == "Only check stats."


def test_example_personas_and_roster_load():
    personas = load_personas(REPO / "examples" / "personas.toml")
    assert {"skeptic", "researcher", "methodologist", "statistician"} <= set(personas)
    roster = load_roster(REPO / "examples" / "agents.toml")
    assert {"astra", "sol", "opus", "sonnet", "haiku"} <= set(roster)
    assert roster["astra"].family == "openai" and roster["opus"].family == "anthropic"
    assert roster["deepseek"].billing == "api" and roster["deepseek"].family == "deepseek"
    assert roster["astra"].workdir == REPO


# Panel rounds (ask)


def test_panel_round_is_blind_and_recorded(hub: Hub):
    room = hub.open_room("Is A1 supported?", ["astra", "sonnet", "fable"], brief="n=500")
    replies = run(hub.ask(room.id, "Review the claim."))

    assert [r.author for r in replies] == ["astra", "sonnet", "fable"]
    for agent in hub.roster.values():
        assert "answer from" not in agent.prompts[0]
        assert "n=500" in agent.prompts[0] and "Review the claim." in agent.prompts[0]
    assert len(hub.store.load(room.id).messages) == 4


def test_visibility_all_shows_peers_by_label_never_by_name(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet", "fable"])
    run(hub.ask(room.id, "First take?"))
    run(hub.ask(room.id, "Respond to the others.", visibility="all"))

    prompt = hub.roster["astra"].prompts[1]
    assert "## Round 1, Reviewer B\n" in prompt and "## Round 1, Reviewer C\n" in prompt
    assert "## Round 1, You\nanswer from astra" in prompt
    assert "## Round 1, sonnet" not in prompt and "## Round 1, fable" not in prompt


def test_ring_and_graph_visibility(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet", "fable"])
    assert room.peers("astra", "ring") == {"fable"}
    assert room.peers("sonnet", "ring") == {"astra"}
    assert room.peers("fable", {"fable": ["astra"]}) == {"astra"}
    with pytest.raises(KeyError):
        room.peers("fable", {"fable": ["nobody"]})
    with pytest.raises(ValueError):
        room.peers("fable", "everyone")


def test_failed_seat_is_recorded_and_hidden_from_others(hub: Hub):
    hub.roster["sonnet"].fail = True
    room = hub.open_room("topic", ["astra", "sonnet"])
    replies = run(hub.ask(room.id, "Go."))
    assert [r.error for r in replies] == [False, True]
    run(hub.ask(room.id, "Again.", visibility="all"))
    assert "failed" not in hub.roster["astra"].prompts[1]


def test_on_reply_reports_each_answer(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet"])
    seen = []
    run(hub.ask(room.id, "Go.", on_reply=lambda message: seen.append(message.author)))
    assert sorted(seen) == ["astra", "sonnet"]


# Discussions (discuss)


def test_discussion_opens_blind_then_takes_turns(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet"])
    outcome = run(hub.discuss(room.id, "Is the split sound?", turns=4))

    assert outcome.status == "paused"
    assert [t.author for t in outcome.turns] == ["astra", "sonnet", "astra", "sonnet"]
    opening, later = hub.roster["astra"].prompts
    assert "answer from sonnet" not in opening
    assert "## Round 1, Reviewer B\nanswer from sonnet" in later
    assert "(Stance: not yet agreed: p; open: x)" in later
    assert "live discussion" in hub.roster["astra"].systems[1]
    assert outcome.turns[0].text == "answer from astra"
    assert outcome.turns[0].stance == {"agree": False, "position": "p", "open": ["x"]}


def test_discussion_stops_when_everyone_agrees(hub: Hub):
    for agent in hub.roster.values():
        agent.agree = True
    room = hub.open_room("topic", ["astra", "sonnet", "fable"])
    outcome = run(hub.discuss(room.id, "Question?", turns=10))
    assert outcome.status == "consensus"
    assert len(outcome.turns) == 3
    assert all(p["agree"] for p in outcome.positions.values())


def test_stop_on_agreement_can_be_turned_off(hub: Hub):
    for agent in hub.roster.values():
        agent.agree = True
    room = hub.open_room("topic", ["astra", "sonnet"])
    outcome = run(hub.discuss(room.id, "Question?", turns=4, stop_on_agreement=False))
    assert len(outcome.turns) == 4


def test_host_message_needs_fresh_agreement_and_can_hand_the_floor(hub: Hub):
    for agent in hub.roster.values():
        agent.agree = True
    room = hub.open_room("topic", ["astra", "sonnet", "fable"])
    run(hub.discuss(room.id, "Question?"))

    outcome = run(hub.discuss(room.id, "@Reviewer C, what about leakage?", turns=1))
    assert [t.author for t in outcome.turns] == ["fable"]
    assert outcome.status == "paused"
    assert "## Round 2, Host\n@Reviewer C, what about leakage?" in hub.roster["fable"].prompts[1]


def test_seats_can_hand_the_floor_to_each_other(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet", "fable"])
    run(hub.discuss(room.id, "Question?", turns=3))
    loaded = hub.store.load(room.id)
    last = loaded.messages[-1]
    loaded.messages[-1] = type(last)(**{**last.__dict__, "text": "I defer to @Reviewer B."})
    assert next_speaker(loaded) == "sonnet"


def test_wrap_up_near_the_turn_limit(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet"])
    run(hub.discuss(room.id, "Question?", turns=3, max_turns=4))
    assert "close to its turn limit (2 seat turns left)" in hub.roster["astra"].prompts[-1]


def test_turn_limit_and_extension(hub: Hub):
    room = hub.open_room("topic", ["astra", "sonnet"])
    first = run(hub.discuss(room.id, "Question?", turns=10, max_turns=3))
    assert (first.status, first.turns_used) == ("turn_limit", 3)

    stuck = run(hub.discuss(room.id, turns=5))
    assert stuck.turns == [] and stuck.status == "turn_limit"

    extended = run(hub.discuss(room.id, turns=2, max_turns=5))
    assert (len(extended.turns), extended.turns_used, extended.status) == (2, 5, "turn_limit")


def test_discussion_preconditions(hub: Hub):
    solo = hub.open_room("topic", ["astra"])
    with pytest.raises(ValueError):
        run(hub.discuss(solo.id, "Question?"))
    pair = hub.open_room("topic", ["astra", "sonnet"])
    with pytest.raises(ValueError):
        run(hub.discuss(pair.id))


def test_stance_parsing():
    text, stance = parse_stance('Fine.\nSTANCE: {"agree": true, "position": "ok", "open": []}')
    assert text == "Fine." and stance == {"agree": True, "position": "ok", "open": []}
    assert parse_stance("No stance here.") == ("No stance here.", None)
    assert parse_stance("Bad.\nSTANCE: {not json}") == ("Bad.", None)
    assert parse_stance('Odd.\nSTANCE: {"agree": "yes"}') == ("Odd.", None)


# Persistence


def test_store_round_trip_and_transcript(hub: Hub):
    room = hub.open_room("Plan review", ["astra:skeptic", "fable"])
    run(hub.discuss(room.id, "Thoughts?", turns=2))
    path = hub.close_room(room.id, "Keep the plan; add a drift control.")

    loaded = hub.store.load(room.id)
    assert loaded.seats[0].persona == "skeptic" and loaded.turns_used == 2
    transcript = path.read_text(encoding="utf-8")
    assert "### astra-skeptic (Reviewer A, skeptic, fake-1, 1s)" in transcript
    assert "> Stance: not yet agreed: p; open: x" in transcript
    assert "## Conclusion" in transcript
    assert hub.store.list() == [room.id]


def test_rooms_saved_before_personas_still_load(hub: Hub):
    room = hub.open_room("topic", ["astra"])
    path = hub.store.root / room.id / "room.json"
    data = json.loads(path.read_text())
    for seat in data["seats"]:
        del seat["agent"], seat["persona"]
    del data["discussion_start"], data["max_turns"]
    path.write_text(json.dumps(data))
    assert hub.store.load(room.id).seats[0].agent == "astra"


# CLI adapters


def test_claude_command_is_read_only_and_isolated():
    command = ClaudeCodeAgent("opus", "opus", Path("/repo"), effort="high").command("rules")
    assert command[command.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--strict-mcp-config" in command
    assert command[command.index("--add-dir") + 1] == "/repo"
    assert command[command.index("--effort") + 1] == "high"


def test_claude_output_parsing():
    ok = json.dumps(
        {"subtype": "success", "is_error": False, "result": "pong", "total_cost_usd": 0.001}
    )
    assert ClaudeCodeAgent.parse(ok)[:2] == ("pong", 0.001)
    bad = json.dumps({"subtype": "error_max_turns", "is_error": True, "result": "stopped"})
    with pytest.raises(AgentError):
        ClaudeCodeAgent.parse(bad)


def test_codex_command_is_read_only():
    command = CodexAgent("sol", "gpt-6.1-sol", Path("/repo"), effort="high").command()
    assert 'sandbox_mode="read-only"' in command
    assert "--ignore-user-config" in command
    assert 'model_reasoning_effort="high"' in command
    assert command[-1] == "-"


def test_codex_output_parsing():
    events = [
        {"type": "thread.started", "thread_id": "t"},
        {"type": "item.completed", "item": {"id": "0", "type": "agent_message", "text": "draft"}},
        {"type": "item.completed", "item": {"id": "1", "type": "agent_message", "text": "final"}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
    ]
    text, usage = CodexAgent.parse("\n".join(json.dumps(e) for e in events))
    assert text == "final" and usage["output_tokens"] == 2
    with pytest.raises(AgentError):
        CodexAgent.parse(json.dumps({"type": "turn.failed", "error": {"message": "x"}}))
