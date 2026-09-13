"""Codex agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.base import BaseAgent


class CodexAgent(BaseAgent):
    binary_name = "codex"
    prompt_via_stdin = True

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        # `--full-auto` was removed in codex-cli 0.154; `--sandbox workspace-write` is the part of it
        # that matters for non-interactive runs and is accepted by older versions too.
        return ["codex", "exec", "--sandbox", "workspace-write", "-C", str(workspace), "-"]
