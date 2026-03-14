"""Claude agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    binary_name = "claude"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["claude", "-p", "--permission-mode", "bypassPermissions", prompt]
