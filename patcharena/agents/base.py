"""Base agent adapter implementation."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Any, Self

from patcharena.models import CommandResult, RunObservation
from patcharena.process import run_command


class BaseAgent:
    """Base adapter for a coding agent CLI."""

    binary_name = ""
    prompt_via_stdin = False
    model: str | None = None
    effort: str | None = None

    def is_available(self) -> bool:
        return shutil.which(self.binary_name) is not None

    def with_settings(self, model: str | None, effort: str | None) -> Self:
        """Return a copy that runs with ``model`` and ``effort``; None keeps the CLI's own default."""
        configured = copy.copy(self)
        configured.model = model
        configured.effort = effort
        return configured

    def setup_workspace(self, workspace: Path) -> list[str]:
        """Inject agent-specific files. Returns paths to exclude from patch."""
        return []

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        raise NotImplementedError

    def observe_run(self, workspace: Path, started_at: float, result: CommandResult) -> RunObservation:
        """Return what the CLI recorded about a run that started at ``started_at``.

        That is the models and effort levels it used, and any errors it recorded even when it exited with
        status 0. The default observes nothing, which leaves pinned settings unverified.
        """
        return RunObservation()

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


def flag(name: str, value: str | None) -> list[str]:
    """Return ``[name, value]``, or an empty list when ``value`` is None."""
    return [] if value is None else [name, value]


def distinct(values: Iterable[object], ignore: Collection[str] = ()) -> list[str]:
    """Return the distinct non-empty strings in ``values``, in first-seen order."""
    return list(dict.fromkeys(value for value in values if isinstance(value, str) and value and value not in ignore))


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse one JSON object, returning an empty dict for anything else."""
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
