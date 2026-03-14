"""Command-line interface for PatchArena."""

from __future__ import annotations

import argparse
from pathlib import Path

from patcharena.runner import run_task_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patcharena")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a benchmark task.")
    run_parser.add_argument("task_file", type=Path, help="Path to task.yaml")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        report = run_task_file(args.task_file)
        print(report.run_dir / "benchmark_report.json")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2
