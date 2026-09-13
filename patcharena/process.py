"""Run commands in their own process group so everything they spawn can be killed."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from patcharena.git_env import git_environment
from patcharena.models import CommandResult
from patcharena.result_parser import command_result_from_run

_POLL_INTERVAL_SECONDS = 0.2

_running_lock = threading.Lock()
_running: set[subprocess.Popen[str]] = set()


def run_command(
    command: Sequence[str] | str,
    cwd: Path,
    *,
    timeout: float | None,
    timeout_message: str,
    input_text: str | None = None,
    shell: bool = False,
) -> CommandResult:
    """Run ``command`` with git signing disabled and capture its outcome.

    A command that times out or cannot start gets ``exit_code=None``; a timeout keeps the partial stdout.
    """
    started_at = time.time()
    try:
        completed = run_process(
            command, cwd, input_text=input_text, timeout=timeout, shell=shell, env=git_environment()
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = exc.output if isinstance(exc.output, str) else ""
        return command_result_from_run(command, None, partial_stdout, timeout_message, time.time() - started_at)
    except OSError as exc:
        return command_result_from_run(command, None, "", str(exc), time.time() - started_at)
    return command_result_from_run(
        command, completed.returncode, completed.stdout, completed.stderr, time.time() - started_at
    )


def run_process(
    command: Sequence[str] | str,
    cwd: Path,
    *,
    input_text: str | None = None,
    timeout: float | None = None,
    shell: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``command`` like ``subprocess.run(..., capture_output=True, text=True)``.

    The command gets its own process group, which is killed once the command
    exits or times out. Background processes it leaves behind therefore cannot
    keep the output pipes open or keep modifying the workspace.

    Raises ``subprocess.TimeoutExpired`` carrying the partial output on timeout.
    """
    started_at = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=cwd,
        shell=shell,
        env=env,
        stdin=subprocess.DEVNULL if input_text is None else subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )
    with _running_lock:
        _running.add(process)
    try:
        pending_input = input_text
        while True:
            try:
                stdout, stderr = process.communicate(pending_input, timeout=_POLL_INTERVAL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pending_input = None
            if process.poll() is not None:
                # The command has exited, but a background process still holds its output pipes.
                _kill_process_group(process)
                stdout, stderr = process.communicate()
                break
            if timeout is not None and time.monotonic() - started_at >= timeout:
                _kill_process_group(process)
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
    finally:
        _kill_process_group(process)
        with _running_lock:
            _running.discard(process)
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def kill_running_processes() -> None:
    """Kill every command started by :func:`run_process` that is still running."""
    with _running_lock:
        processes = list(_running)
    for process in processes:
        _kill_process_group(process)


def _kill_process_group(process: subprocess.Popen[str]) -> None:
    if not hasattr(os, "killpg"):
        process.kill()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # The group is already gone (macOS reports PermissionError when only zombies remain).
        pass
