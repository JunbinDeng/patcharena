"""Agent registry for PatchArena."""

from patcharena.agents.base import BaseAgent
from patcharena.agents.claude import ClaudeAgent
from patcharena.agents.codex import CodexAgent


def get_agent_registry() -> dict[str, BaseAgent]:
    return {
        "codex": CodexAgent(),
        "claude": ClaudeAgent(),
    }
