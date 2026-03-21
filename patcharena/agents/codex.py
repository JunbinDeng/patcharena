"""Codex agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class CodexAgent(BaseAgent):
    name = "codex"
    binary_name = "codex"
    prompt_via_stdin = True

    def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
        return ["codex", "exec", "--full-auto", "-C", str(workspace), "-"]
