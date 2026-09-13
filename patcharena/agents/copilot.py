"""GitHub Copilot CLI adapter."""

from __future__ import annotations

import os
from pathlib import Path

from patcharena.agents.base import BaseAgent, distinct, flag, parse_json_object
from patcharena.models import CommandResult, RunObservation


class CopilotAgent(BaseAgent):
    binary_name = "copilot"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return [
            "copilot",
            "-p",
            prompt,
            "--allow-all-tools",
            *flag("--model", self.model),
            *flag("--effort", self.effort),
        ]

    def observe_run(self, workspace: Path, started_at: float, result: CommandResult) -> RunObservation:
        del result
        # Copilot CLI keeps an event log per session, next to a workspace.yaml that names the session's cwd.
        home = Path(os.environ.get("COPILOT_HOME", Path.home() / ".copilot"))
        cwd_line = f"cwd: {workspace.resolve()}"
        models: list[object] = []
        efforts: list[object] = []
        for workspace_file in (home / "session-state").glob("*/workspace.yaml"):
            events = workspace_file.with_name("events.jsonl")
            if not events.exists() or events.stat().st_mtime < started_at:
                continue
            if cwd_line not in workspace_file.read_text(encoding="utf-8").splitlines():
                continue
            for line in events.read_text(encoding="utf-8").splitlines():
                event = parse_json_object(line)
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                if event.get("type") == "assistant.message":
                    models.append(data.get("model"))
                elif event.get("type") == "session.model_change":
                    efforts.append(data.get("reasoningEffort"))
        return RunObservation(models=distinct(models), efforts=distinct(efforts))
