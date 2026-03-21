from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from patcharena.agents import get_agent_registry
from patcharena.agents.base import BaseAgent
from patcharena.cli import main
from patcharena.models import (
    CommandResult,
    DEFAULT_AGENT_TIMEOUT,
    DEFAULT_AGENTS,
    TaskConfig,
)
from patcharena.patch import extract_patch
from patcharena.result_parser import parse_shortstat
from patcharena.runner import run_task_file
from patcharena.workspace import WorkspaceManager


class FakeAgent(BaseAgent):
    name = "fake"
    binary_name = "fake"

    def is_available(self) -> bool:
        return True

    def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
        return ["fake"]

    def run(self, task_prompt: str, workspace: Path, patch_only: bool = False, timeout: int | None = None) -> CommandResult:
        target = workspace / "hello.txt"
        target.write_text("done\n", encoding="utf-8")
        return CommandResult(
            command="fake",
            exit_code=0,
            passed=True,
            stdout="fake stdout",
            stderr="",
            duration_seconds=0.01,
        )


class AlwaysAvailableAgent(BaseAgent):
    """Agent that always reports as available and delegates to BaseAgent.run."""

    name = "always"
    binary_name = "always"

    def is_available(self) -> bool:
        return True

    def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
        return ["always", prompt]


class RelativePathAgent(BaseAgent):
    name = "relative"
    binary_name = "path-check"

    def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
        return ["path-check", str(workspace)]


class TaskConfigTests(unittest.TestCase):
    def test_from_file_rejects_name_with_path_separator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for bad_name in ["../escape", "task/subtask", ".."]:
                task_file = root / "task.yaml"
                task_file.write_text(
                    f"name: {bad_name!r}\nrepo_path: ./repo\nprompt: test\n",
                    encoding="utf-8",
                )
                with self.assertRaises(ValueError, msg=f"name {bad_name!r} should be rejected"):
                    TaskConfig.from_file(task_file)

    def test_from_file_applies_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: sample-task",
                        "repo_path: ./repo",
                        "prompt: Fix the bug",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = TaskConfig.from_file(task_file)

            self.assertEqual(config.name, "sample-task")
            self.assertEqual(config.repo_path, (root / "repo").resolve())
            self.assertEqual(config.prompt, "Fix the bug")
            self.assertEqual(config.compile_command, "")
            self.assertEqual(config.test_command, "")
            self.assertEqual(config.agents, DEFAULT_AGENTS)

    def test_constants_are_exported(self) -> None:
        self.assertIsInstance(DEFAULT_AGENT_TIMEOUT, int)
        self.assertGreater(DEFAULT_AGENT_TIMEOUT, 0)
        self.assertIsInstance(DEFAULT_AGENTS, list)
        self.assertTrue(all(isinstance(a, str) for a in DEFAULT_AGENTS))

    def test_direct_constructor_and_from_file_share_defaults(self) -> None:
        """Both code paths must use the same default values."""
        # Direct constructor
        direct = TaskConfig(name="t", repo_path=Path("."), prompt="p")
        self.assertEqual(direct.agent_timeout, DEFAULT_AGENT_TIMEOUT)
        self.assertEqual(direct.agents, DEFAULT_AGENTS)

        # from_file() with no optional fields
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.yaml"
            task_file.write_text(
                "name: t\nrepo_path: ./repo\nprompt: p\n",
                encoding="utf-8",
            )
            loaded = TaskConfig.from_file(task_file)
        self.assertEqual(loaded.agent_timeout, DEFAULT_AGENT_TIMEOUT)
        self.assertEqual(loaded.agents, DEFAULT_AGENTS)

    def test_from_file_accepts_all_supported_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: sample-task",
                        "repo_path: ./repo",
                        "prompt: Fix the bug",
                        "agents:",
                        "  - codex",
                        "  - claude",
                        "  - opencode",
                        "  - copilot",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = TaskConfig.from_file(task_file)

            self.assertEqual(
                config.agents,
                ["codex", "claude", "opencode", "copilot"],
            )


class AgentRegistryTests(unittest.TestCase):
    def test_registry_includes_all_supported_agents(self) -> None:
        registry = get_agent_registry()

        self.assertEqual(
            sorted(registry),
            ["claude", "codex", "copilot", "opencode"],
        )


class BaseAgentTests(unittest.TestCase):
    def test_run_resolves_relative_workspace_before_building_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "runs" / "task" / "agent"
            workspace.mkdir(parents=True)

            script = root / "path-check"
            script.write_text(
                "\n".join(
                    [
                        "#!/bin/sh",
                        'if [ -d "$1" ]; then',
                        "  exit 0",
                        "fi",
                        "exit 1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            script.chmod(0o755)

            previous_cwd = Path.cwd()
            try:
                os.chdir(root)
                with mock.patch.dict(
                    os.environ,
                    {"PATH": f"{root}{os.pathsep}{os.environ.get('PATH', '')}"},
                ):
                    result = RelativePathAgent().run("ignored", Path("runs/task/agent"))
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(result.passed)


class AgentTimeoutTests(unittest.TestCase):
    def test_timeout_reason_propagated_to_compile_and_test_stderr(self) -> None:
        """Agent returning exit_code=None should thread its stderr into compile/test stderr."""

        class TimedOutAgent(BaseAgent):
            name = "timedout"
            binary_name = "timedout"

            def is_available(self) -> bool:
                return True

            def build_command(self, prompt: str, workspace: Path, patch_only: bool = False) -> list[str]:
                return ["timedout"]

            def run(self, task_prompt: str, workspace: Path, patch_only: bool = False, timeout: int | None = None) -> CommandResult:
                del task_prompt, patch_only, timeout
                return CommandResult(
                    command="timedout",
                    exit_code=None,
                    passed=False,
                    stdout="",
                    stderr="Agent timed out after 1 seconds",
                    duration_seconds=1.0,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: timeout-propagation-task",
                        f"repo_path: {source_repo}",
                        "prompt: Test",
                        "agents:",
                        "  - timedout",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_task_file(
                task_file,
                runs_root=root / "runs",
                agent_registry={"timedout": TimedOutAgent()},
            )

            result = report.results[0]
            self.assertEqual(result.status, "error")
            self.assertIn("timed out", result.compile_result.stderr.lower())
            self.assertIn("timed out", result.test_result.stderr.lower())

    def test_run_returns_error_result_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            with mock.patch(
                "patcharena.agents.base.subprocess.run",
                side_effect=subprocess.TimeoutExpired("fake", 1),
            ):
                result = AlwaysAvailableAgent().run("ignored", workspace, timeout=1)

            self.assertIsNone(result.exit_code)
            self.assertFalse(result.passed)
            self.assertIn("timed out", result.stderr.lower())

    def test_task_config_loads_agent_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: timeout-task",
                        "repo_path: ./repo",
                        "prompt: Test",
                        "agent_timeout: 120",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            config = TaskConfig.from_file(task_file)

            self.assertEqual(config.agent_timeout, 120)


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
                self.assertEqual(
                    (stats.files_changed, stats.insertions, stats.deletions),
                    expected,
                )


class WorkspaceTests(unittest.TestCase):
    def test_prepare_appends_patcharena_content_when_agents_md_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            (source_repo / "AGENTS.md").write_text("# Project rules\n- Keep it simple\n", encoding="utf-8")
            commit_file(source_repo, "AGENTS.md")
            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="agents-test", repo_path=source_repo, prompt="Make a change")

            prepared = manager.prepare(task, "codex")

            agents_content = (prepared.path / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Keep it simple", agents_content)
            self.assertIn("PatchArena Workspace", agents_content)
            self.assertIn("AGENTS.md", prepared.excluded_patch_paths)

    def test_prepare_writes_patch_only_instruction_when_agents_md_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            (source_repo / "AGENTS.md").write_text("# Project rules\n", encoding="utf-8")
            commit_file(source_repo, "AGENTS.md")
            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="patch-only-test", repo_path=source_repo, prompt="Make a change")

            prepared = manager.prepare(task, "codex", patch_only=True)

            agents_content = (prepared.path / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Do not run shell commands", agents_content)

    def test_prepare_works_with_plain_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            source_dir.mkdir()
            (source_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="plain-dir-task", repo_path=source_dir, prompt="Make a change")

            prepared = manager.prepare(task, "codex")

            self.assertTrue((prepared.path / ".git").exists())
            self.assertTrue((prepared.path / "main.py").exists())

    def test_prepare_clones_repo_and_writes_task_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="task-one", repo_path=source_repo, prompt="Make a change")

            prepared = manager.prepare(task, "codex")

            self.assertTrue((prepared.path / ".git").exists())
            self.assertTrue(prepared.task_file.exists())
            self.assertTrue((prepared.path / "AGENTS.md").exists())
            self.assertIn("PATCHARENA_TASK.md", prepared.excluded_patch_paths)
            self.assertIn("AGENTS.md", prepared.excluded_patch_paths)
            self.assertIn("Make a change", prepared.task_file.read_text(encoding="utf-8"))


class PatchTests(unittest.TestCase):
    def test_extract_patch_handles_non_utf8_file_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="binary-test", repo_path=source_repo, prompt="Add latin-1 file")
            prepared = manager.prepare(task, "codex")

            # Write a file with latin-1 bytes that are invalid UTF-8 (no null, so git treats as text)
            (prepared.path / "latin1.txt").write_bytes(b"caf\xe9\n")

            stats = extract_patch(
                prepared.path,
                prepared.patch_file,
                excluded_paths=prepared.excluded_patch_paths,
            )

            self.assertGreater(stats.files_changed, 0)

    def test_extract_patch_writes_fix_patch_and_counts_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            manager = WorkspaceManager(root / "runs")
            task = TaskConfig(name="task-two", repo_path=source_repo, prompt="Update files")
            prepared = manager.prepare(task, "codex")

            tracked_file = prepared.path / "README.md"
            tracked_file.write_text("hello\nupdated\n", encoding="utf-8")
            (prepared.path / "new_file.txt").write_text("brand new\n", encoding="utf-8")

            stats = extract_patch(
                prepared.path,
                prepared.patch_file,
                excluded_paths=prepared.excluded_patch_paths,
            )

            patch_text = prepared.patch_file.read_text(encoding="utf-8")
            self.assertGreater(stats.patch_lines, 0)
            self.assertEqual(stats.files_changed, 2)
            self.assertIn("new_file.txt", patch_text)
            self.assertNotIn("PATCHARENA_TASK.md", patch_text)


class RunnerTests(unittest.TestCase):
    def test_error_result_propagates_reason_to_compile_and_test_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: error-task",
                        f"repo_path: {root / 'does_not_exist'}",
                        "prompt: Test",
                        "agents:",
                        "  - fake",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_task_file(
                task_file,
                runs_root=root / "runs",
                agent_registry={"fake": FakeAgent()},
            )

            result = report.results[0]
            self.assertEqual(result.status, "error")
            self.assertIn("does not exist", result.agent_result.stderr)
            self.assertIn("does not exist", result.compile_result.stderr)
            self.assertIn("does not exist", result.test_result.stderr)

    def test_run_task_file_rejects_duplicate_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: dup-task",
                        f"repo_path: {source_repo}",
                        "prompt: Test",
                        "agents:",
                        "  - fake",
                        "  - fake",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError, msg="duplicate agent names should raise ValueError"):
                run_task_file(
                    task_file,
                    runs_root=root / "runs",
                    agent_registry={"fake": FakeAgent()},
                )

    def test_run_task_file_writes_json_report_with_fake_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: report-task",
                        f"repo_path: {source_repo}",
                        "prompt: Add hello.txt",
                        "compile_command: test -f hello.txt",
                        "test_command: grep -q done hello.txt",
                        "agents:",
                        "  - fake",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = run_task_file(
                task_file,
                runs_root=root / "runs",
                agent_registry={"fake": FakeAgent()},
            )

            report_path = report.run_dir / "benchmark_report.json"
            payload = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(report.results[0].status, "success")
            self.assertTrue(report.results[0].compile_result.passed)
            self.assertTrue(report.results[0].test_result.passed)
            self.assertTrue(report.results[0].patch_file.exists())
            self.assertEqual(payload["results"][0]["agent"], "fake")
            self.assertEqual(payload["results"][0]["agent_command"], "fake")
            self.assertEqual(payload["results"][0]["agent_stdout"], "fake stdout")
            self.assertEqual(payload["results"][0]["agent_stderr"], "")
            self.assertEqual(payload["results"][0]["compile_stderr"], "")
            self.assertEqual(payload["results"][0]["test_stderr"], "")
            self.assertEqual(payload["summary"]["successful_agents"], 1)


class CliTests(unittest.TestCase):
    def test_cli_entrypoint_runs_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_repo = create_git_repo(root / "source")
            task_file = root / "task.yaml"
            task_file.write_text(
                "\n".join(
                    [
                        "name: cli-task",
                        f"repo_path: {source_repo}",
                        "prompt: Add hello.txt",
                        "compile_command: test -f hello.txt",
                        "test_command: grep -q done hello.txt",
                        "agents:",
                        "  - fake",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            def run_in_temp(task_path: Path):
                return run_task_file(
                    task_path,
                    runs_root=root / "runs",
                    agent_registry={"fake": FakeAgent()},
                )

            with mock.patch("patcharena.cli.run_task_file", side_effect=run_in_temp):
                exit_code = main(["run", str(task_file)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "runs" / "cli-task" / "benchmark_report.json").exists())


def create_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], path)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    run(["git", "add", "README.md"], path)
    run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "user.name=PatchArena",
            "-c",
            "user.email=patcharena@example.com",
            "commit",
            "-m",
            "Initial commit",
        ],
        path,
    )
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
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


if __name__ == "__main__":
    unittest.main()
