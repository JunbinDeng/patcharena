"""Base agent adapter implementation."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from patcharena.models import CommandResult
from patcharena.result_parser import command_result_from_run


class BaseAgent:
    """Base adapter for a coding agent CLI."""

    name = ""
    binary_name = ""
    prompt_via_stdin = False

    def is_available(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        raise NotImplementedError

    def run(self, task_prompt: str, workspace: Path) -> CommandResult:
        workspace = workspace.resolve()
        command = self.build_command(task_prompt, workspace)
        if not self.is_available():
            return CommandResult(
                command=" ".join(command),
                exit_code=None,
                passed=False,
                stdout="",
                stderr=f"Executable not found: {self.binary_name}",
                duration_seconds=0.0,
            )

        started_at = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                input=task_prompt if self.prompt_via_stdin else None,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            return CommandResult(
                command=" ".join(command),
                exit_code=None,
                passed=False,
                stdout="",
                stderr=str(exc),
                duration_seconds=time.time() - started_at,
            )

        return command_result_from_run(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.time() - started_at,
        )
