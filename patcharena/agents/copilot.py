"""Placeholder GitHub Copilot adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class CopilotAgent(BaseAgent):
    name = "copilot"
    binary_name = "copilot"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["copilot", "agent", prompt]
