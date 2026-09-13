"""Base agent adapter implementation."""

from __future__ import annotations

import shutil
from pathlib import Path

from patcharena.models import CommandResult
from patcharena.process import run_command


class BaseAgent:
    """Base adapter for a coding agent CLI."""

    binary_name = ""
    prompt_via_stdin = False

    def is_available(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def setup_workspace(self, workspace: Path) -> list[str]:
        """Inject agent-specific files. Returns paths to exclude from patch."""
        return []

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        raise NotImplementedError

    def run(self, task_prompt: str, workspace: Path, timeout: float | None = None) -> CommandResult:
        workspace = workspace.resolve()
        command = self.build_command(task_prompt, workspace)
        if not self.is_available():
            return CommandResult.failed(f"Executable not found: {self.binary_name}", command=" ".join(command))
        return run_command(
            command,
            workspace,
            timeout=timeout,
            timeout_message=f"Agent timed out after {timeout} seconds",
            input_text=task_prompt if self.prompt_via_stdin else None,
        )
