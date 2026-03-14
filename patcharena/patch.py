"""Patch extraction helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess

from patcharena.git_env import git_environment
from patcharena.models import PatchStats
from patcharena.result_parser import parse_shortstat


def extract_patch(
    workspace: Path,
    patch_file: Path,
    excluded_paths: list[str] | None = None,
) -> PatchStats:
    excluded_paths = excluded_paths or []
    _run_git(["git", "add", "-N", "."], workspace)

    diff_command = ["git", "diff", "--binary", *pathspec_args(excluded_paths)]
    diff_text = _run_git(diff_command, workspace)
    patch_file.write_text(diff_text, encoding="utf-8")

    shortstat_text = _run_git(
        ["git", "diff", "--shortstat", *pathspec_args(excluded_paths)],
        workspace,
    )
    stats = parse_shortstat(shortstat_text)
    stats.patch_lines = len(diff_text.splitlines())
    return stats


def pathspec_args(excluded_paths: list[str]) -> list[str]:
    args = ["--", "."]
    for path in excluded_paths:
        args.append(f":(exclude){path}")
    return args


def _run_git(command: list[str], workspace: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
        env=git_environment(),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git command failed")
    return completed.stdout
