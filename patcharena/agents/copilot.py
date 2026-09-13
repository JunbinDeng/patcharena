"""GitHub Copilot CLI adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class CopilotAgent(BaseAgent):
    binary_name = "copilot"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["copilot", "-p", prompt, "--allow-all-tools"]
