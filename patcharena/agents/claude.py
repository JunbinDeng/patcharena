"""Claude agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    binary_name = "claude"

    def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
        permission_mode = "acceptEdits" if patch_only else "bypassPermissions"
        return ["claude", "-p", "--permission-mode", permission_mode, prompt]
