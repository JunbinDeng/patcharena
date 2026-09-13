"""Claude agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    binary_name = "claude"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        del workspace
        # Grant tools on the command line: Claude Code ignores permissions in a project's
        # .claude/settings.json until the trust dialog is accepted for that directory,
        # and every benchmark workspace is a new directory.
        return ["claude", "-p", prompt, "--allowedTools", "Edit,Write,Bash"]
