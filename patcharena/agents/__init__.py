"""Agent registry for PatchArena."""

from patcharena.agents.base import BaseAgent
from patcharena.agents.claude import ClaudeAgent
from patcharena.agents.claude_bedrock import ClaudeBedrockAgent
from patcharena.agents.codex import CodexAgent
from patcharena.agents.copilot import CopilotAgent
from patcharena.agents.opencode import OpenCodeAgent


def get_agent_registry(
    agent_options: dict[str, dict] | None = None,
) -> dict[str, BaseAgent]:
    opts = agent_options or {}
    bedrock_opts = opts.get("claude-bedrock", {})
    return {
        "codex": CodexAgent(),
        "claude": ClaudeAgent(),
        "claude-bedrock": ClaudeBedrockAgent(**bedrock_opts),
        "opencode": OpenCodeAgent(),
        "copilot": CopilotAgent(),
    }
