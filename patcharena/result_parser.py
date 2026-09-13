"""Small parsing helpers for command and diff results."""

from __future__ import annotations

import re
from collections.abc import Sequence

from patcharena.models import CommandResult, PatchStats


def command_result_from_run(
    command: Sequence[str] | str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    duration_seconds: float,
) -> CommandResult:
    return CommandResult(
        command=command if isinstance(command, str) else " ".join(command),
        exit_code=exit_code,
        passed=exit_code == 0,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=duration_seconds,
    )


def parse_shortstat(shortstat: str) -> PatchStats:
    text = shortstat.strip()
    if not text:
        return PatchStats()

    files_changed = _extract_count(text, r"(\d+)\s+files?\s+changed")
    insertions = _extract_count(text, r"(\d+)\s+insertions?\(\+\)")
    deletions = _extract_count(text, r"(\d+)\s+deletions?\(-\)")

    return PatchStats(
        patch_lines=0,
        files_changed=files_changed,
        insertions=insertions,
        deletions=deletions,
    )


def _extract_count(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    if not match:
        return 0
    return int(match.group(1))
