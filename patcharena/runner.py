"""Main benchmark orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import time

from patcharena.agents import get_agent_registry
from patcharena.agents.base import BaseAgent
from patcharena.models import AgentRunResult, CommandResult, PatchStats, TaskConfig
from patcharena.patch import extract_patch
from patcharena.report import build_report, write_report
from patcharena.result_parser import command_result_from_run
from patcharena.workspace import PreparedWorkspace, WorkspaceManager


def run_task_file(
    task_file: Path,
    runs_root: Path | None = None,
    agent_registry: dict[str, BaseAgent] | None = None,
):
    task = TaskConfig.from_file(task_file)
    runs_root = Path("runs") if runs_root is None else Path(runs_root)
    registry = agent_registry or get_agent_registry()

    seen: set[str] = set()
    duplicates = [name for name in task.agents if name in seen or seen.add(name)]  # type: ignore[func-returns-value]
    if duplicates:
        raise ValueError(f"duplicate agents in task: {', '.join(sorted(set(duplicates)))}")

    missing_agents = [name for name in task.agents if name not in registry]
    if missing_agents:
        names = ", ".join(missing_agents)
        supported = ", ".join(sorted(registry))
        raise ValueError(
            f"unknown agents requested: {names}. Supported agents: {supported}"
        )

    workspace_manager = WorkspaceManager(runs_root)
    run_dir = workspace_manager.run_dir(task.name)
    run_dir.mkdir(parents=True, exist_ok=True)

    results_by_agent: dict[str, AgentRunResult] = {}
    max_workers = max(1, len(task.agents))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_agent_benchmark,
                task,
                registry[agent_name],
                workspace_manager,
            ): agent_name
            for agent_name in task.agents
        }
        for future in as_completed(futures):
            agent_name = futures[future]
            results_by_agent[agent_name] = future.result()

    ordered_results = [results_by_agent[agent_name] for agent_name in task.agents]
    report = build_report(task, run_dir, ordered_results)
    write_report(report, run_dir / "benchmark_report.json")
    return report


def _run_agent_benchmark(
    task: TaskConfig,
    agent: BaseAgent,
    workspace_manager: WorkspaceManager,
) -> AgentRunResult:
    workspace = None
    try:
        workspace = workspace_manager.prepare(task, agent.name, task.patch_only)
        agent_result = agent.run(task.prompt, workspace.path, task.patch_only, timeout=task.agent_timeout)

        if agent_result.exit_code is None:
            compile_result = skipped_result("validation skipped because the agent did not start")
            test_result = skipped_result("validation skipped because the agent did not start")
            patch_stats = extract_patch(
                workspace.path,
                workspace.patch_file,
                excluded_paths=workspace.excluded_patch_paths,
            )
            return AgentRunResult(
                agent=agent.name,
                runtime_seconds=agent_result.duration_seconds,
                patch_stats=patch_stats,
                compile_result=compile_result,
                test_result=test_result,
                agent_result=agent_result,
                status="error",
                workspace=workspace.path,
                patch_file=workspace.patch_file,
            )

        compile_result = run_validation(task.compile_command, workspace.path)
        test_result = run_validation(task.test_command, workspace.path)
        patch_stats = extract_patch(
            workspace.path,
            workspace.patch_file,
            excluded_paths=workspace.excluded_patch_paths,
        )
        status = determine_status(agent_result, compile_result, test_result)
        return AgentRunResult(
            agent=agent.name,
            runtime_seconds=agent_result.duration_seconds,
            patch_stats=patch_stats,
            compile_result=compile_result,
            test_result=test_result,
            agent_result=agent_result,
            status=status,
            workspace=workspace.path,
            patch_file=workspace.patch_file,
        )
    except Exception as exc:
        return error_result(task, agent.name, workspace_manager, workspace, str(exc))


def run_validation(command: str, workspace: Path) -> CommandResult:
    if not command.strip():
        return CommandResult(
            command="",
            exit_code=0,
            passed=True,
            stdout="",
            stderr="",
            duration_seconds=0.0,
        )

    started_at = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return CommandResult(
            command=command,
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


def determine_status(
    agent_result: CommandResult,
    compile_result: CommandResult,
    test_result: CommandResult,
) -> str:
    if agent_result.exit_code is None:
        return "error"
    if agent_result.exit_code != 0:
        return "agent_failed"
    if compile_result.passed and test_result.passed:
        return "success"
    return "validation_failed"


def skipped_result(message: str) -> CommandResult:
    return CommandResult(
        command="",
        exit_code=None,
        passed=False,
        stdout="",
        stderr=message,
        duration_seconds=0.0,
    )


def error_result(
    task: TaskConfig,
    agent_name: str,
    workspace_manager: WorkspaceManager,
    workspace: PreparedWorkspace | None,
    message: str,
) -> AgentRunResult:
    agent_result = CommandResult(
        command="",
        exit_code=None,
        passed=False,
        stdout="",
        stderr=message,
        duration_seconds=0.0,
    )
    compile_result = skipped_result("validation skipped because the run failed")
    test_result = skipped_result("validation skipped because the run failed")

    if workspace is None:
        workspace_path = workspace_manager.workspace_dir(task.name, agent_name)
        patch_file = workspace_manager.patch_path(task.name, agent_name)
    else:
        workspace_path = workspace.path
        patch_file = workspace.patch_file

    return AgentRunResult(
        agent=agent_name,
        runtime_seconds=0.0,
        patch_stats=PatchStats(),
        compile_result=compile_result,
        test_result=test_result,
        agent_result=agent_result,
        status="error",
        workspace=workspace_path,
        patch_file=patch_file,
    )
