"""Patch extraction helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

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

    # Keep the diff as bytes: decoding it would corrupt files that are not valid UTF-8.
    diff = _run_git(["git", "diff", "--binary", *pathspec_args(excluded_paths)], workspace)
    patch_file.write_bytes(diff)

    shortstat = _run_git(
        ["git", "diff", "--shortstat", *pathspec_args(excluded_paths)],
        workspace,
    )
    stats = parse_shortstat(shortstat.decode("utf-8", errors="replace"))
    stats.patch_lines = len(diff.splitlines())
    return stats


def pathspec_args(excluded_paths: list[str]) -> list[str]:
    args = ["--", "."]
    for path in excluded_paths:
        args.append(f":(exclude){path}")
    return args


def _run_git(command: list[str], workspace: Path) -> bytes:
    completed = subprocess.run(
        command,
        cwd=workspace,
        capture_output=True,
        check=False,
        env=git_environment(),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace").strip() or "git command failed")
    return completed.stdout
