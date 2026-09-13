"""Codex agent adapter."""

from __future__ import annotations

import re
from pathlib import Path

from patcharena.agents.base import BaseAgent, distinct, flag
from patcharena.models import CommandResult, RunObservation

_HEADER_RULE = re.compile(r"(?m)^-{4,}\s*$")


class CodexAgent(BaseAgent):
    binary_name = "codex"
    prompt_via_stdin = True

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        # `--full-auto` was removed in codex-cli 0.154; `--sandbox workspace-write` is the part of it
        # that matters for non-interactive runs and is accepted by older versions too.
        effort = [] if self.effort is None else ["-c", f'model_reasoning_effort="{self.effort}"']
        return [
            "codex",
            "exec",
            "--sandbox",
            "workspace-write",
            *flag("--model", self.model),
            *effort,
            "-C",
            str(workspace),
            "-",
        ]

    def observe_run(self, workspace: Path, started_at: float, result: CommandResult) -> RunObservation:
        del workspace, started_at
        # `codex exec` prints its effective configuration on stderr, between the first two rules. The
        # header comes before the first request, so it also appears when the API rejects the model;
        # only a successful run shows that the settings were in effect.
        if result.exit_code != 0:
            return RunObservation()
        sections = _HEADER_RULE.split(result.stderr)
        header = sections[1] if len(sections) >= 3 else ""
        return RunObservation(
            models=distinct(re.findall(r"(?m)^model: (\S+)\s*$", header)),
            efforts=distinct(re.findall(r"(?m)^reasoning effort: (\S+)\s*$", header)),
        )
