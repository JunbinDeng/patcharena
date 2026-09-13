"""JSON reporting helpers."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean

from patcharena.models import AgentRunResult, AgentSummary, BenchmarkReport, TaskConfig


def build_report(
    task: TaskConfig,
    run_dir: Path,
    results: list[AgentRunResult],
    source_has_uncommitted_changes: bool,
) -> BenchmarkReport:
    results_by_id: dict[str, list[AgentRunResult]] = {}
    for result in results:
        results_by_id.setdefault(result.spec.id, []).append(result)
    return BenchmarkReport(
        task_name=task.name,
        source_repo=task.repo_path,
        run_dir=run_dir,
        repeat=task.repeat,
        hidden_tests=task.hidden_tests,
        source_has_uncommitted_changes=source_has_uncommitted_changes,
        agents=[_summarize_agent(agent_results) for agent_results in results_by_id.values()],
        results=results,
    )


def write_report(report: BenchmarkReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


def pass_at_k(runs: int, successes: int, k: int) -> float:
    """Estimate the chance that at least one of ``k`` runs succeeds, from ``runs`` observed runs.

    Uses the unbiased estimator from "Evaluating Large Language Models Trained on Code" (Chen et al., 2021).
    """
    if runs - successes < k:
        return 1.0
    return 1.0 - math.comb(runs - successes, k) / math.comb(runs, k)


def _summarize_agent(results: list[AgentRunResult]) -> AgentSummary:
    runs = len(results)
    successes = sum(1 for result in results if result.status == "success")
    return AgentSummary(
        spec=results[0].spec,
        runs=runs,
        successful_runs=successes,
        pass_at_k={k: pass_at_k(runs, successes, k) for k in range(1, runs + 1)},
        status_counts=dict(Counter(result.status for result in results)),
        settings_checks=dict(Counter(result.settings_check for result in results)),
        mean_runtime_seconds=fmean(result.runtime_seconds for result in results),
        mean_patch_lines=fmean(result.patch_stats.patch_lines for result in results),
    )
