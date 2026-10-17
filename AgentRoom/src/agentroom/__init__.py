"""Agent rooms: put several local agents in a room and let the main agent discuss with them.

Agents are subscription coding CLIs (Claude Code, Codex) or a deepagents harness on
OpenRouter. The main Claude Code session reaches rooms through the MCP server in
:mod:`agentroom.server`; people can use the same rooms from the ``agentroom`` CLI.
"""
