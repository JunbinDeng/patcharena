"""Command-line interface for PatchArena."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from patcharena.models import BenchmarkReport
from patcharena.runner import run_task_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patcharena")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a benchmark task.")
    run_parser.add_argument("task_file", type=Path, help="Path to task.yaml")
    run_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the results of a previous run of the same task.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Exit with 0 when every run of every agent succeeds, 1 when any does not, 2 on invalid input."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            report = run_task_file(args.task_file, overwrite=args.overwrite)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"patcharena: error: {exc}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("patcharena: interrupted", file=sys.stderr)
            return 130
        print(report.run_dir / "benchmark_report.json")
        _print_warnings(report)
        return 0 if all(result.status == "success" for result in report.results) else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def _print_warnings(report: BenchmarkReport) -> None:
    if report.source_has_uncommitted_changes:
        print(
            f"patcharena: warning: {report.source_repo} has uncommitted changes; "
            "agent workspaces only contain committed files",
            file=sys.stderr,
        )
