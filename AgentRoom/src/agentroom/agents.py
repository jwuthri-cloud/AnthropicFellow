"""Agents a room can seat, behind one small interface.

Every agent is stateless: each turn it receives a system prompt and a full prompt built by
the room, so the room decides exactly what each agent sees and the transcript records it.
All agents get read-only access to one working directory and no way to open rooms
themselves.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

Billing = Literal["subscription", "api"]


class AgentError(RuntimeError):
    """An agent failed to produce a reply."""


@dataclass(frozen=True)
class Reply:
    """One agent turn."""

    text: str
    seconds: float
    cost_usd: float | None = None
    usage: dict = field(default_factory=dict)


class Agent(Protocol):
    """Anything that can take a turn in a room."""

    name: str
    model: str

    @property
    def family(self) -> str: ...

    @property
    def billing(self) -> Billing: ...

    async def respond(self, system: str, prompt: str) -> Reply: ...


async def run_cli(command: list[str], stdin: str, cwd: Path, timeout_s: float) -> str:
    """Run a CLI with the prompt on stdin and return stdout; raise AgentError on failure."""
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin.encode()), timeout_s)
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise AgentError(f"{command[0]} timed out after {timeout_s:.0f}s") from error
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()[-500:]
        raise AgentError(f"{command[0]} exited with {process.returncode}: {detail}")
    return stdout.decode(errors="replace")


@dataclass(frozen=True)
class ClaudeCodeAgent:
    """A Claude Code seat (``claude -p``) on the user's subscription, read-only tools only."""

    name: str
    model: str
    workdir: Path
    effort: str | None = None
    timeout_s: float = 900

    family: ClassVar[str] = "anthropic"
    billing: ClassVar[Billing] = "subscription"

    def command(self, system: str) -> list[str]:
        """Build the CLI call; the prompt goes on stdin."""
        command = [
            "claude",
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--append-system-prompt",
            system,
            "--tools",
            "Read,Glob,Grep",
            "--add-dir",
            str(self.workdir),
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--no-session-persistence",
        ]
        if self.effort:
            command += ["--effort", self.effort]
        return command

    @staticmethod
    def parse(stdout: str) -> tuple[str, float | None, dict]:
        """Extract text, cost and usage from ``--output-format json``."""
        result = json.loads(stdout)
        if result.get("is_error") or result.get("subtype") != "success":
            raise AgentError(f"claude returned an error: {str(result.get('result'))[:500]}")
        return result["result"], result.get("total_cost_usd"), result.get("usage", {})

    async def respond(self, system: str, prompt: str) -> Reply:
        """Answer one turn."""
        start = time.monotonic()
        # A neutral cwd keeps the project's CLAUDE.md (and its room tools) out of the seat.
        with tempfile.TemporaryDirectory(prefix="agentroom-") as cwd:
            stdout = await run_cli(self.command(system), prompt, Path(cwd), self.timeout_s)
        text, cost, usage = self.parse(stdout)
        return Reply(text, time.monotonic() - start, cost, usage)


@dataclass(frozen=True)
class CodexAgent:
    """A Codex seat (``codex exec``) on the user's subscription, read-only sandbox."""

    name: str
    model: str
    workdir: Path
    effort: str | None = None
    timeout_s: float = 900

    family: ClassVar[str] = "openai"
    billing: ClassVar[Billing] = "subscription"

    def command(self) -> list[str]:
        """Build the CLI call; the prompt goes on stdin."""
        command = [
            "codex",
            "exec",
            "--json",
            "--model",
            self.model,
            "--config",
            'sandbox_mode="read-only"',
            "--cd",
            str(self.workdir),
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--ephemeral",
        ]
        if self.effort:
            command += ["--config", f'model_reasoning_effort="{self.effort}"']
        return [*command, "-"]

    @staticmethod
    def parse(stdout: str) -> tuple[str, dict]:
        """Extract the final agent message and usage from ``--json`` event lines."""
        text, usage = None, {}
        for line in stdout.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            kind = event.get("type")
            item = event.get("item", {})
            if kind == "item.completed" and item.get("type") == "agent_message":
                text = item["text"]
            elif kind == "turn.completed":
                usage = event.get("usage", {})
            elif kind in {"error", "turn.failed"}:
                raise AgentError(f"codex failed: {json.dumps(event)[:500]}")
        if text is None:
            raise AgentError("codex produced no agent message")
        return text, usage

    async def respond(self, system: str, prompt: str) -> Reply:
        """Answer one turn. Codex has no system-prompt flag, so the room rules lead the prompt."""
        start = time.monotonic()
        stdout = await run_cli(
            self.command(), f"{system}\n\n---\n\n{prompt}", self.workdir, self.timeout_s
        )
        text, usage = self.parse(stdout)
        return Reply(text, time.monotonic() - start, None, usage)


@dataclass(frozen=True)
class DeepAgent:
    """A deepagents harness on an API model (``openrouter:<model>`` and so on), paid per token."""

    name: str
    model: str
    workdir: Path
    max_steps: int = 40

    billing: ClassVar[Billing] = "api"

    @property
    def family(self) -> str:
        """Model maker, e.g. ``deepseek`` for ``openrouter:deepseek/deepseek-v4``."""
        return self.model.split(":", 1)[-1].split("/", 1)[0]

    def build(self, system: str) -> Any:
        """Create the deepagents graph: repo mounted read-only at /repo/, secrets unreadable."""
        from deepagents import FilesystemPermission, create_deep_agent
        from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend

        backend = CompositeBackend(
            default=StateBackend(),
            routes={"/repo/": FilesystemBackend(root_dir=str(self.workdir), virtual_mode=True)},
        )
        permissions = [
            FilesystemPermission(
                operations=["read"], paths=["/**/.env*", "/**/*.key"], mode="deny"
            ),
            FilesystemPermission(operations=["write"], paths=["/repo/**"], mode="deny"),
        ]
        prompt = f"{system}\n\nThe research repository is mounted read-only at /repo/."
        return create_deep_agent(
            model=self.model, system_prompt=prompt, backend=backend, permissions=permissions
        )

    async def respond(self, system: str, prompt: str) -> Reply:
        """Answer one turn."""
        start = time.monotonic()
        graph = self.build(system)
        state = await graph.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": self.max_steps},
        )
        final = state["messages"][-1]
        usage = dict(getattr(final, "usage_metadata", None) or {})
        return Reply(str(final.content), time.monotonic() - start, None, usage)
