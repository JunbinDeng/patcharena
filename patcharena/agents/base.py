"""Base agent adapter implementation."""

from __future__ import annotations

import os
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

    def setup_workspace(self, workspace: Path) -> list[str]:
        """Inject agent-specific files. Returns paths to exclude from patch."""
        return []

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        raise NotImplementedError

    def extra_env(self) -> dict[str, str | None]:
        """Extra environment variables for the agent subprocess.
        A None value means the key is explicitly unset (removed from the environment)."""
        return {}

    def run(
        self,
        task_prompt: str,
        workspace: Path,
        timeout: int | None = None,
    ) -> CommandResult:
        workspace = workspace.resolve()
        command = self.build_command(task_prompt, workspace)
        env_prefix = " ".join(
            f"{k}={v}" for k, v in self.extra_env().items() if v is not None
        )
        command_str = f"{env_prefix} {' '.join(command)}" if env_prefix else " ".join(command)
        if not self.is_available():
            return CommandResult(
                command=command_str,
                exit_code=None,
                passed=False,
                stdout="",
                stderr=f"Executable not found: {self.binary_name}",
                duration_seconds=0.0,
            )

        env = dict(os.environ)
        for key, value in self.extra_env().items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        started_at = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                input=task_prompt if self.prompt_via_stdin else None,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command_str,
                exit_code=None,
                passed=False,
                stdout="",
                stderr=f"Agent timed out after {timeout} seconds",
                duration_seconds=time.time() - started_at,
            )
        except OSError as exc:
            return CommandResult(
                command=command_str,
                exit_code=None,
                passed=False,
                stdout="",
                stderr=str(exc),
                duration_seconds=time.time() - started_at,
            )

        return command_result_from_run(
            command=command_str,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.time() - started_at,
        )
