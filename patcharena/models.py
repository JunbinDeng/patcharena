"""Dataclasses for PatchArena."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


DEFAULT_AGENT_TIMEOUT: int = 1800
DEFAULT_AGENTS: list[str] = ["codex", "claude"]


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

    @classmethod
    def from_file(cls, task_file: Path) -> "TaskConfig":
        task_path = Path(task_file).resolve()
        data = yaml.safe_load(task_path.read_text(encoding="utf-8")) or {}

        name = _require_string(data, "name")
        name_parts = Path(name).parts
        if len(name_parts) != 1 or name_parts[0] in (".", ".."):
            raise ValueError(
                f"task 'name' must be a single path component without separators: {name!r}"
            )
        repo_value = _require_string(data, "repo_path")
        prompt = _require_string(data, "prompt")
        compile_command = _optional_string(data.get("compile_command"))
        test_command = _optional_string(data.get("test_command"))
        agents = _agent_list(data.get("agents"))
        agent_timeout = _positive_int(data.get("agent_timeout"), default=DEFAULT_AGENT_TIMEOUT, field="agent_timeout")

        repo_path = Path(repo_value)
        if not repo_path.is_absolute():
            repo_path = (task_path.parent / repo_path).resolve()

        return cls(
            name=name,
            repo_path=repo_path,
            prompt=prompt,
            compile_command=compile_command,
            test_command=test_command,
            agents=agents,
            agent_timeout=agent_timeout,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "repo_path": str(self.repo_path),
            "prompt": self.prompt,
            "compile_command": self.compile_command,
            "test_command": self.test_command,
            "agents": list(self.agents),
            "agent_timeout": self.agent_timeout,
        }


@dataclass(slots=True)
class CommandResult:
    """Captured outcome for a shell command."""

    command: str
    exit_code: int | None
    passed: bool
    stdout: str
    stderr: str
    duration_seconds: float

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
    status: str
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
            "compile_stderr": self.compile_result.stderr,
            "test_exit_code": self.test_result.exit_code,
            "test_command": self.test_result.command,
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
    results: list[AgentRunResult]
    summary: dict[str, float | int]

    def to_dict(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "source_repo": str(self.source_repo),
            "run_dir": str(self.run_dir),
            "results": [result.to_dict() for result in self.results],
            "summary": dict(self.summary),
        }


def _require_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"task file must define a non-empty '{key}' string")
    return value.strip()


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("optional task commands must be strings")
    return value.strip()


def _positive_int(value: object, default: int, field: str = "value") -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"'{field}' must be a positive integer (seconds)")
    return value


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
    return agents
