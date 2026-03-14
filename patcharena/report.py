"""JSON reporting helpers."""

from __future__ import annotations

import json
from pathlib import Path

from patcharena.models import AgentRunResult, BenchmarkReport, TaskConfig


def build_report(task: TaskConfig, run_dir: Path, results: list[AgentRunResult]) -> BenchmarkReport:
    return BenchmarkReport(
        task_name=task.name,
        source_repo=task.repo_path,
        run_dir=run_dir,
        results=results,
        summary=_build_summary(results),
    )


def write_report(report: BenchmarkReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def _build_summary(results: list[AgentRunResult]) -> dict[str, float | int]:
    agent_count = len(results)
    successful_agents = sum(1 for result in results if result.status == "success")
    total_runtime = sum(result.runtime_seconds for result in results)
    total_patch_lines = sum(result.patch_stats.patch_lines for result in results)

    return {
        "agent_count": agent_count,
        "successful_agents": successful_agents,
        "success_rate": round(successful_agents / agent_count, 3) if agent_count else 0.0,
        "average_runtime_seconds": round(total_runtime / agent_count, 3) if agent_count else 0.0,
        "average_patch_lines": round(total_patch_lines / agent_count, 3) if agent_count else 0.0,
    }
