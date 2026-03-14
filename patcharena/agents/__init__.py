"""Agent registry for PatchArena."""

from patcharena.agents.base import BaseAgent
from patcharena.agents.claude import ClaudeAgent
from patcharena.agents.codex import CodexAgent
from patcharena.agents.copilot import CopilotAgent
from patcharena.agents.opencode import OpenCodeAgent


def get_agent_registry() -> dict[str, BaseAgent]:
    return {
        "codex": CodexAgent(),
        "claude": ClaudeAgent(),
        "opencode": OpenCodeAgent(),
        "copilot": CopilotAgent(),
    }
