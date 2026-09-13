"""Main benchmark orchestration."""

from __future__ import annotations

import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from patcharena.agents import get_agent_registry
from patcharena.agents.base import BaseAgent
from patcharena.models import AgentRunResult, BenchmarkReport, CommandResult, PatchStats, Status, TaskConfig
from patcharena.patch import extract_patch
from patcharena.process import kill_running_processes, run_command
from patcharena.report import build_report, write_report
from patcharena.workspace import PreparedWorkspace, WorkspaceManager, has_uncommitted_changes


def run_task_file(
    task_file: Path,
    runs_root: Path | None = None,
    agent_registry: dict[str, BaseAgent] | None = None,
    overwrite: bool = False,
) -> BenchmarkReport:
    task = TaskConfig.from_file(task_file)
    runs_root = Path("runs") if runs_root is None else Path(runs_root)
    registry = agent_registry or get_agent_registry()

    missing_agents = [name for name in task.agents if name not in registry]
    if missing_agents:
        names = ", ".join(missing_agents)
        supported = ", ".join(sorted(registry))
        raise ValueError(
            f"unknown agents requested: {names}. Supported agents: {supported}"
        )

    workspace_manager = WorkspaceManager(runs_root)
    run_dir = workspace_manager.run_dir(task.name)
    if run_dir.exists():
        if not overwrite:
            raise FileExistsError(f"run directory already exists: {run_dir} (use --overwrite to replace it)")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    source_has_uncommitted_changes = has_uncommitted_changes(task.repo_path)

    results_by_agent: dict[str, AgentRunResult] = {}
    cancelled = threading.Event()
    executor = ThreadPoolExecutor(max_workers=max(1, len(task.agents)))
    try:
        futures = {
            executor.submit(
                _run_agent_benchmark,
                task,
                agent_name,
                registry[agent_name],
                workspace_manager,
                cancelled,
            ): agent_name
            for agent_name in task.agents
        }
        for future in as_completed(futures):
            results_by_agent[futures[future]] = future.result()
    except BaseException:
        # Agent processes run in their own process groups, so Ctrl+C never reaches them.
        cancelled.set()
        kill_running_processes()
        raise
    finally:
        executor.shutdown(cancel_futures=True)

    results = [results_by_agent[agent_name] for agent_name in task.agents]
    report = build_report(task, run_dir, results, source_has_uncommitted_changes)
    write_report(report, run_dir / "benchmark_report.json")
    return report


def _run_agent_benchmark(
    task: TaskConfig,
    agent_name: str,
    agent: BaseAgent,
    workspace_manager: WorkspaceManager,
    cancelled: threading.Event,
) -> AgentRunResult:
    workspace = None
    try:
        workspace = workspace_manager.prepare(task, agent_name)
        workspace.excluded_patch_paths.extend(agent.setup_workspace(workspace.path))
        agent_result = agent.run(task.prompt, workspace.path, timeout=task.agent_timeout)

        # Extract the patch before validation so build and test artifacts stay out of it.
        patch_stats = extract_patch(
            workspace.path,
            workspace.patch_file,
            excluded_paths=workspace.excluded_patch_paths,
        )

        if agent_result.exit_code is None:
            compile_result = test_result = CommandResult.failed(f"validation skipped: {agent_result.stderr}")
        else:
            _raise_if_cancelled(cancelled)
            compile_result = run_validation(task.compile_command, workspace.path, task.validation_timeout)
            _raise_if_cancelled(cancelled)
            test_result = run_validation(task.test_command, workspace.path, task.validation_timeout)

        return AgentRunResult(
            agent=agent_name,
            runtime_seconds=agent_result.duration_seconds,
            patch_stats=patch_stats,
            compile_result=compile_result,
            test_result=test_result,
            agent_result=agent_result,
            status=determine_status(agent_result, compile_result, test_result),
            workspace=workspace.path,
            patch_file=workspace.patch_file,
        )
    except Exception as exc:
        return error_result(task, agent_name, workspace_manager, workspace, str(exc))


def _raise_if_cancelled(cancelled: threading.Event) -> None:
    if cancelled.is_set():
        raise RuntimeError("benchmark interrupted")


def run_validation(command: str, workspace: Path, timeout: float) -> CommandResult:
    if not command.strip():
        return CommandResult(command="", exit_code=0, passed=True, stdout="", stderr="", duration_seconds=0.0)
    return run_command(
        command,
        workspace,
        shell=True,
        timeout=timeout,
        timeout_message=f"Command timed out after {timeout} seconds",
    )


def determine_status(
    agent_result: CommandResult,
    compile_result: CommandResult,
    test_result: CommandResult,
) -> Status:
    if agent_result.exit_code is None:
        return "error"
    if agent_result.exit_code != 0:
        return "agent_failed"
    if compile_result.passed and test_result.passed:
        return "success"
    return "validation_failed"


def error_result(
    task: TaskConfig,
    agent_name: str,
    workspace_manager: WorkspaceManager,
    workspace: PreparedWorkspace | None,
    message: str,
) -> AgentRunResult:
    if workspace is None:
        workspace_path = workspace_manager.workspace_dir(task.name, agent_name)
        patch_file = workspace_manager.patch_path(task.name, agent_name)
    else:
        workspace_path = workspace.path
        patch_file = workspace.patch_file

    skipped = CommandResult.failed(f"validation skipped: {message}")
    return AgentRunResult(
        agent=agent_name,
        runtime_seconds=0.0,
        patch_stats=PatchStats(),
        compile_result=skipped,
        test_result=skipped,
        agent_result=CommandResult.failed(message),
        status="error",
        workspace=workspace_path,
        patch_file=patch_file,
    )
