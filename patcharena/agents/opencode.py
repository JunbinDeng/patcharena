"""OpenCode agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class OpenCodeAgent(BaseAgent):
    name = "opencode"
    binary_name = "opencode"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["opencode", "run", "--dir", str(workspace), prompt]
