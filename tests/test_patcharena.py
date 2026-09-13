from __future__ import annotations

import contextlib
import functools
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import yaml

from patcharena import process
from patcharena.agents import get_agent_registry
from patcharena.agents.base import BaseAgent
from patcharena.agents.claude import ClaudeAgent
from patcharena.agents.codex import CodexAgent
from patcharena.agents.copilot import CopilotAgent
from patcharena.agents.opencode import OpenCodeAgent
from patcharena.cli import main
from patcharena.models import (
    DEFAULT_AGENT_TIMEOUT,
    DEFAULT_AGENTS,
    DEFAULT_VALIDATION_TIMEOUT,
    BenchmarkReport,
    CommandResult,
    TaskConfig,
)
from patcharena.patch import extract_patch
from patcharena.result_parser import parse_shortstat
from patcharena.runner import run_task_file, run_validation
from patcharena.workspace import PreparedWorkspace, WorkspaceManager


class FakeAgent(BaseAgent):
    """Writes hello.txt and succeeds, without running a CLI."""

    def run(self, task_prompt: str, workspace: Path, timeout: float | None = None) -> CommandResult:
        (workspace / "hello.txt").write_text("done\n", encoding="utf-8")
        return CommandResult(
            command="fake", exit_code=0, passed=True, stdout="fake stdout", stderr="", duration_seconds=0.01
        )


class TimedOutAgent(FakeAgent):
    def run(self, task_prompt: str, workspace: Path, timeout: float | None = None) -> CommandResult:
        return CommandResult.failed("Agent timed out after 1 seconds", command="timedout", duration_seconds=1.0)


class ShellAgent(BaseAgent):
    """Runs a shell script through BaseAgent.run."""

    binary_name = "sh"

    def __init__(self, script: str) -> None:
        self.script = script

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["sh", "-c", self.script]


class RelativePathAgent(BaseAgent):
    binary_name = "path-check"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["path-check", str(workspace)]


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))

    @functools.cached_property
    def source_repo(self) -> Path:
        return create_git_repo(self.root / "source")

    def write_task(self, file_name: str = "task.yaml", **fields: object) -> Path:
        """Write a task file; repo_path defaults to a fresh git repository."""
        task = {"name": "task", "prompt": "Test", **fields}
        task.setdefault("repo_path", str(self.source_repo))
        path = self.root / file_name
        path.write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")
        return path

    def run_task(
        self,
        task_file: Path,
        agents: dict[str, BaseAgent],
        overwrite: bool = False,
    ) -> tuple[BenchmarkReport, dict[str, Any]]:
        report = run_task_file(task_file, runs_root=self.root / "runs", agent_registry=agents, overwrite=overwrite)
        payload = json.loads((report.run_dir / "benchmark_report.json").read_text(encoding="utf-8"))
        return report, payload

    def prepare_workspace(self, source: Path, agent: str = "codex") -> PreparedWorkspace:
        task = TaskConfig(name="workspace-task", repo_path=source, prompt="Make a change")
        return WorkspaceManager(self.root / "runs").prepare(task, agent)


class TaskConfigTests(TempDirTestCase):
    def test_from_file_applies_defaults(self) -> None:
        config = TaskConfig.from_file(self.write_task(repo_path="./repo"))

        self.assertEqual((config.name, config.prompt), ("task", "Test"))
        self.assertEqual(config.repo_path, (self.root / "repo").resolve())
        self.assertEqual((config.compile_command, config.test_command), ("", ""))
        self.assertEqual(config.agents, DEFAULT_AGENTS)
        self.assertEqual(
            (config.agent_timeout, config.validation_timeout),
            (DEFAULT_AGENT_TIMEOUT, DEFAULT_VALIDATION_TIMEOUT),
        )

    def test_from_file_loads_optional_fields(self) -> None:
        task_file = self.write_task(
            repo_path="./repo",
            agent_timeout=120,
            validation_timeout=90,
            agents=["codex", "copilot"],
        )

        config = TaskConfig.from_file(task_file)

        self.assertEqual((config.agent_timeout, config.validation_timeout), (120, 90))
        self.assertEqual(config.agents, ["codex", "copilot"])

    def test_from_file_rejects_invalid_values(self) -> None:
        cases: dict[str, dict[str, object]] = {
            "name with a separator": {"name": "../escape"},
            "boolean timeout": {"agent_timeout": True},
            "agent entry of the wrong type": {"agents": [42]},
            "duplicate agents": {"agents": ["codex", "codex"]},
        }

        for case, fields in cases.items():
            with self.subTest(case):
                task_file = self.write_task(**{"repo_path": "./repo", **fields})

                with self.assertRaises(ValueError):
                    TaskConfig.from_file(task_file)


class AgentRegistryTests(unittest.TestCase):
    def test_registry_includes_all_supported_agents(self) -> None:
        self.assertEqual(sorted(get_agent_registry()), ["claude", "codex", "copilot", "opencode"])


class AgentCommandTests(unittest.TestCase):
    def test_commands_pass_workspace_and_prompt_to_each_cli(self) -> None:
        cases: dict[str, tuple[BaseAgent, list[str]]] = {
            "claude": (ClaudeAgent(), ["claude", "-p", "Fix", "--allowedTools", "Edit,Write,Bash"]),
            "codex": (CodexAgent(), ["codex", "exec", "--sandbox", "workspace-write", "-C", "/tmp/ws", "-"]),
            "copilot": (CopilotAgent(), ["copilot", "-p", "Fix", "--allow-all-tools"]),
            "opencode": (OpenCodeAgent(), ["opencode", "run", "--dir", "/tmp/ws", "Fix"]),
        }

        for name, (agent, expected) in cases.items():
            with self.subTest(name):
                self.assertEqual(agent.build_command("Fix", Path("/tmp/ws")), expected)
        self.assertTrue(CodexAgent.prompt_via_stdin)


class BaseAgentTests(TempDirTestCase):
    def test_run_resolves_relative_workspace_before_building_command(self) -> None:
        (self.root / "runs" / "task" / "agent").mkdir(parents=True)
        script = self.root / "path-check"
        script.write_text('#!/bin/sh\nif [ -d "$1" ]; then\n  exit 0\nfi\nexit 1\n', encoding="utf-8")
        script.chmod(0o755)

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with mock.patch.dict(os.environ, {"PATH": f"{self.root}{os.pathsep}{os.environ.get('PATH', '')}"}):
                result = RelativePathAgent().run("ignored", Path("runs/task/agent"))
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(result.exit_code, 0)

    def test_run_disables_gpg_signing_for_agent_git_commands(self) -> None:
        result = ShellAgent("git config --get commit.gpgsign").run("ignored", self.root)

        self.assertEqual(result.stdout.strip(), "false")

    def test_run_does_not_wait_for_background_processes_after_exit(self) -> None:
        started_at = time.monotonic()
        result = ShellAgent("sleep 30 & echo done").run("ignored", self.root, timeout=8)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("done", result.stdout)
        self.assertLess(time.monotonic() - started_at, 5)

    def test_timeouts_keep_partial_output(self) -> None:
        results = {
            "agent": ShellAgent("echo partial; sleep 30").run("ignored", self.root, timeout=0.3),
            "validation": run_validation("echo partial; sleep 30", self.root, timeout=0.3),
        }

        for caller, result in results.items():
            with self.subTest(caller):
                self.assertIsNone(result.exit_code)
                self.assertFalse(result.passed)
                self.assertIn("timed out", result.stderr.lower())
                self.assertIn("partial", result.stdout)

    def test_timeout_kills_background_processes(self) -> None:
        ShellAgent("sleep 30 & echo $! > child.pid; wait").run("ignored", self.root, timeout=0.3)

        child_pid = int((self.root / "child.pid").read_text(encoding="utf-8"))
        self.assertTrue(wait_for_exit(child_pid), "background process survived the timeout")

    def test_kill_running_processes_stops_active_commands(self) -> None:
        outcomes: list[subprocess.CompletedProcess[str]] = []
        thread = threading.Thread(target=lambda: outcomes.append(process.run_process(["sleep", "30"], self.root)))
        thread.start()
        deadline = time.monotonic() + 5
        while not process._running and time.monotonic() < deadline:
            time.sleep(0.01)

        process.kill_running_processes()
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertNotEqual(outcomes[0].returncode, 0)


class ResultParserTests(unittest.TestCase):
    def test_parse_shortstat_handles_edge_cases(self) -> None:
        cases = [
            ("", (0, 0, 0)),
            ("1 file changed, 2 insertions(+), 1 deletion(-)", (1, 2, 1)),
            ("2 files changed, 3 insertions(+)", (2, 3, 0)),
            ("1 file changed, 4 deletions(-)", (1, 0, 4)),
        ]

        for shortstat, expected in cases:
            with self.subTest(shortstat=shortstat):
                stats = parse_shortstat(shortstat)
                self.assertEqual((stats.files_changed, stats.insertions, stats.deletions), expected)


class WorkspaceTests(TempDirTestCase):
    def test_prepare_clones_repo_and_writes_task_file(self) -> None:
        prepared = self.prepare_workspace(self.source_repo)

        self.assertTrue((prepared.path / ".git").exists())
        self.assertIn("Make a change", prepared.task_file.read_text(encoding="utf-8"))
        self.assertTrue((prepared.path / "AGENTS.md").exists())
        self.assertEqual(prepared.excluded_patch_paths, ["PATCHARENA_TASK.md", "AGENTS.md"])

    def test_prepare_appends_patcharena_content_when_agents_md_exists(self) -> None:
        (self.source_repo / "AGENTS.md").write_text("# Project rules\n- Keep it simple\n", encoding="utf-8")
        commit_file(self.source_repo, "AGENTS.md")

        agents_content = (self.prepare_workspace(self.source_repo).path / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("Keep it simple", agents_content)
        self.assertIn("PatchArena Workspace", agents_content)

    def test_prepare_copies_plain_directory(self) -> None:
        source = self.root / "plain"
        source.mkdir()
        (source / "main.py").write_text("print('hello')\n", encoding="utf-8")

        prepared = self.prepare_workspace(source)

        self.assertTrue((prepared.path / ".git").exists())
        self.assertTrue((prepared.path / "main.py").exists())

    def test_prepare_exports_committed_subdirectory_of_git_repo(self) -> None:
        package = self.source_repo / "pkg"
        package.mkdir()
        (package / "module.py").write_text("x = 1\n", encoding="utf-8")
        commit_file(self.source_repo, "pkg")
        (package / "scratch.txt").write_text("not committed\n", encoding="utf-8")

        prepared = self.prepare_workspace(package)

        self.assertTrue((prepared.path / ".git").exists())
        self.assertEqual((prepared.path / "module.py").read_text(encoding="utf-8"), "x = 1\n")
        self.assertFalse((prepared.path / "scratch.txt").exists())
        self.assertFalse((prepared.path / "README.md").exists())

    def test_prepare_copies_untracked_directory_inside_git_repo(self) -> None:
        scratch = self.source_repo / "scratch"
        scratch.mkdir()
        (scratch / "notes.txt").write_text("draft\n", encoding="utf-8")

        prepared = self.prepare_workspace(scratch)

        self.assertTrue((prepared.path / ".git").exists())
        self.assertTrue((prepared.path / "notes.txt").exists())


class PatchTests(TempDirTestCase):
    def test_extract_patch_writes_fix_patch_and_counts_changes(self) -> None:
        prepared = self.prepare_workspace(self.source_repo)
        (prepared.path / "README.md").write_text("hello\nupdated\n", encoding="utf-8")
        (prepared.path / "new_file.txt").write_text("brand new\n", encoding="utf-8")

        stats = extract_patch(prepared.path, prepared.patch_file, excluded_paths=prepared.excluded_patch_paths)

        patch_text = prepared.patch_file.read_text(encoding="utf-8")
        self.assertGreater(stats.patch_lines, 0)
        self.assertEqual(stats.files_changed, 2)
        self.assertIn("new_file.txt", patch_text)
        self.assertNotIn("PATCHARENA_TASK.md", patch_text)

    def test_extract_patch_preserves_non_utf8_file_content(self) -> None:
        prepared = self.prepare_workspace(self.source_repo)
        # Latin-1 bytes that are invalid UTF-8 (no null, so git treats the file as text).
        (prepared.path / "latin1.txt").write_bytes(b"caf\xe9\n")

        extract_patch(prepared.path, prepared.patch_file, excluded_paths=prepared.excluded_patch_paths)

        fresh = self.prepare_workspace(self.source_repo, agent="fresh")
        run(["git", "apply", str(prepared.patch_file)], fresh.path)
        self.assertEqual((fresh.path / "latin1.txt").read_bytes(), b"caf\xe9\n")


class RunnerTests(TempDirTestCase):
    def test_run_task_file_writes_report_with_patch_and_validation_output(self) -> None:
        task_file = self.write_task(
            compile_command="test -f hello.txt && echo built > build.out",
            test_command="grep done hello.txt",
            agents=["fake"],
        )

        report, payload = self.run_task(task_file, {"fake": FakeAgent()})

        expected = {
            "agent": "fake",
            "status": "success",
            "compile_passed": True,
            "tests_passed": True,
            "agent_stdout": "fake stdout",
            "test_stdout": "done\n",
        }
        result = payload["results"][0]
        self.assertEqual({key: result[key] for key in expected}, expected)
        self.assertEqual(payload["summary"]["successful_agents"], 1)
        patch_text = report.results[0].patch_file.read_text(encoding="utf-8")
        self.assertIn("hello.txt", patch_text)
        self.assertNotIn("build.out", patch_text)

    def test_failed_runs_propagate_the_reason_to_skipped_validation(self) -> None:
        cases = {
            "missing repository": (
                self.write_task("missing.yaml", name="missing", repo_path=str(self.root / "missing"), agents=["agent"]),
                FakeAgent(),
                "does not exist",
            ),
            "timed out agent": (
                self.write_task("timed-out.yaml", name="timed-out", agents=["agent"]),
                TimedOutAgent(),
                "timed out",
            ),
        }

        for case, (task_file, agent, reason) in cases.items():
            with self.subTest(case):
                report, _ = self.run_task(task_file, {"agent": agent})

                result = report.results[0]
                self.assertEqual(result.status, "error")
                for command_result in (result.agent_result, result.compile_result, result.test_result):
                    self.assertIn(reason, command_result.stderr.lower())

    def test_reruns_require_overwrite_and_record_uncommitted_source_changes(self) -> None:
        task_file = self.write_task(agents=["fake"])
        report, _ = self.run_task(task_file, {"fake": FakeAgent()})
        self.assertFalse(report.source_has_uncommitted_changes)

        with self.assertRaises(FileExistsError):
            self.run_task(task_file, {"fake": FakeAgent()})

        (self.source_repo / "README.md").write_text("edited\n", encoding="utf-8")
        report, payload = self.run_task(task_file, {"fake": FakeAgent()}, overwrite=True)
        self.assertEqual(report.results[0].status, "success")
        self.assertTrue(payload["source_has_uncommitted_changes"])


class CliTests(TempDirTestCase):
    def test_exit_codes(self) -> None:
        cases: dict[str, tuple[dict[str, object], int]] = {
            "every agent succeeds": ({"test_command": "true", "agents": ["fake"]}, 0),
            "an agent fails validation": ({"test_command": "false", "agents": ["fake"]}, 1),
            "invalid task file": ({"prompt": ""}, 2),
        }

        for index, (case, (fields, expected)) in enumerate(cases.items()):
            with self.subTest(case):
                task_file = self.write_task(f"cli-{index}.yaml", name=f"cli-{index}", **fields)

                exit_code, stdout, stderr = self.run_cli(task_file)

                self.assertEqual(exit_code, expected)
                if expected == 2:
                    self.assertIn("prompt", stderr)
                else:
                    self.assertIn("benchmark_report.json", stdout)

    def run_cli(self, task_file: Path) -> tuple[int, str, str]:
        def run_in_temp(task_path: Path, **kwargs: Any) -> BenchmarkReport:
            return run_task_file(
                task_path, runs_root=self.root / "runs", agent_registry={"fake": FakeAgent()}, **kwargs
            )

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch("patcharena.cli.run_task_file", side_effect=run_in_temp),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = main(["run", str(task_file)])
        return exit_code, stdout.getvalue(), stderr.getvalue()


def wait_for_exit(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def create_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    commit_file(path, "README.md", "Initial commit")
    return path


def commit_file(repo: Path, filename: str, message: str = "Add file") -> None:
    run(["git", "add", filename], repo)
    run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
         "-c", "user.name=Test", "-c", "user.email=test@test.com",
         "commit", "-m", message],
        repo,
    )


def run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


if __name__ == "__main__":
    unittest.main()
