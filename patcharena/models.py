"""Dataclasses for PatchArena."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

DEFAULT_AGENT_TIMEOUT: int = 1800
DEFAULT_VALIDATION_TIMEOUT: int = 600
DEFAULT_AGENTS: list[str] = ["codex", "claude"]

Status = Literal["success", "validation_failed", "agent_failed", "error"]


@dataclass(slots=True)
class TaskConfig:
    """Configuration loaded from a task YAML file."""

    name: str
    repo_path: Path
    prompt: str
    compile_command: str = ""
    test_command: str = ""
    agents: list[str] = field(default_factory=lambda: list(DEFAULT_AGENTS))
    agent_timeout: int = DEFAULT_AGENT_TIMEOUT
    validation_timeout: int = DEFAULT_VALIDATION_TIMEOUT

    @classmethod
    def from_file(cls, task_file: Path) -> TaskConfig:
        task_path = Path(task_file).resolve()
        data = yaml.safe_load(task_path.read_text(encoding="utf-8")) or {}

        return cls(
            name=_require_path_component(_require_string(data, "name"), "task 'name'"),
            repo_path=_resolve_path(task_path, _require_string(data, "repo_path")),
            prompt=_require_string(data, "prompt"),
            compile_command=_optional_string(data.get("compile_command"), field="compile_command"),
            test_command=_optional_string(data.get("test_command"), field="test_command"),
            agents=_agent_list(data.get("agents")),
            agent_timeout=_positive_int(data.get("agent_timeout"), DEFAULT_AGENT_TIMEOUT, field="agent_timeout"),
            validation_timeout=_positive_int(
                data.get("validation_timeout"),
                DEFAULT_VALIDATION_TIMEOUT,
                field="validation_timeout",
            ),
        )


@dataclass(slots=True)
class CommandResult:
    """Captured outcome for a shell command."""

    command: str
    exit_code: int | None
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float

    @classmethod
    def failed(cls, message: str, command: str = "", duration_seconds: float = 0.0) -> CommandResult:
        """Return the result of a command that did not run to completion, with ``message`` as stderr."""
        return cls(
            command=command,
            exit_code=None,
            passed=False,
            stdout="",
            stderr=message,
            duration_seconds=duration_seconds,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "passed": self.passed,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": round(self.duration_seconds, 3),
        }


@dataclass(slots=True)
class PatchStats:
    """Diff statistics for a workspace."""

    patch_lines: int = 0
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "patch_lines": self.patch_lines,
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


@dataclass(slots=True)
class AgentRunResult:
    """Final benchmark result for one agent."""

    agent: str
    runtime_seconds: float
    patch_stats: PatchStats
    compile_result: CommandResult
    test_result: CommandResult
    agent_result: CommandResult
    status: Status
    workspace: Path
    patch_file: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "runtime_seconds": round(self.runtime_seconds, 3),
            "patch_lines": self.patch_stats.patch_lines,
            "files_changed": self.patch_stats.files_changed,
            "insertions": self.patch_stats.insertions,
            "deletions": self.patch_stats.deletions,
            "tests_passed": self.test_result.passed,
            "compile_passed": self.compile_result.passed,
            "status": self.status,
            "agent_exit_code": self.agent_result.exit_code,
            "agent_command": self.agent_result.command,
            "agent_stdout": self.agent_result.stdout,
            "agent_stderr": self.agent_result.stderr,
            "compile_exit_code": self.compile_result.exit_code,
            "compile_command": self.compile_result.command,
            "compile_stdout": self.compile_result.stdout,
            "compile_stderr": self.compile_result.stderr,
            "test_exit_code": self.test_result.exit_code,
            "test_command": self.test_result.command,
            "test_stdout": self.test_result.stdout,
            "test_stderr": self.test_result.stderr,
            "workspace": str(self.workspace),
            "patch_file": str(self.patch_file),
        }


@dataclass(slots=True)
class BenchmarkReport:
    """Top-level report written to disk."""

    task_name: str
    source_repo: Path
    run_dir: Path
    source_has_uncommitted_changes: bool
    results: list[AgentRunResult]
    summary: dict[str, float | int]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "source_repo": str(self.source_repo),
            "run_dir": str(self.run_dir),
            "source_has_uncommitted_changes": self.source_has_uncommitted_changes,
            "results": [result.to_dict() for result in self.results],
            "summary": dict(self.summary),
        }


def _require_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"task file must define a non-empty '{key}' string")
    return value.strip()


def _require_path_component(value: str, label: str) -> str:
    parts = Path(value).parts
    if len(parts) != 1 or parts[0] in (".", ".."):
        raise ValueError(f"{label} must be a single path component without separators: {value!r}")
    return value


def _optional_string(value: object, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"'{field}' must be a string")
    return value.strip()


def _positive_int(value: object, default: int, field: str) -> int:
    if value is None:
        return default
    # bool is a subclass of int, so `agent_timeout: true` would otherwise mean 1 second.
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"'{field}' must be a positive integer")
    return value


def _resolve_path(task_path: Path, value: str) -> Path:
    """Resolve ``value`` relative to the directory containing the task file."""
    path = Path(value)
    if not path.is_absolute():
        path = (task_path.parent / path).resolve()
    return path


def _agent_list(value: object) -> list[str]:
    if value is None:
        return list(DEFAULT_AGENTS)
    if not isinstance(value, list) or not value:
        raise ValueError("'agents' must be a non-empty list of strings")

    agents: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("'agents' must contain only non-empty strings")
        agents.append(item.strip())
    duplicates = sorted(name for name, count in Counter(agents).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate agents in task: {', '.join(duplicates)}")
    return agents
