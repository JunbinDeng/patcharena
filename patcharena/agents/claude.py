"""Claude agent adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path

from patcharena.agents.base import BaseAgent, distinct, flag, parse_json_object
from patcharena.models import CommandResult, RunObservation


class ClaudeAgent(BaseAgent):
    binary_name = "claude"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        del workspace
        # Grant tools on the command line: Claude Code ignores permissions in a project's
        # .claude/settings.json until the trust dialog is accepted for that directory,
        # and every benchmark workspace is a new directory.
        return [
            "claude",
            "-p",
            prompt,
            "--allowedTools",
            "Edit,Write,Bash",
            *flag("--model", self.model),
            *flag("--effort", self.effort),
        ]

    def observe_run(self, workspace: Path, started_at: float, result: CommandResult) -> RunObservation:
        del result
        # Claude Code writes one transcript per session into a directory named after the working
        # directory. Assistant messages carry the model; every entry carries the effort level.
        config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
        project_dir = config_dir / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(workspace.resolve()))
        models: list[object] = []
        efforts: list[object] = []
        for transcript in project_dir.glob("*.jsonl"):
            if transcript.stat().st_mtime < started_at:
                continue
            for line in transcript.read_text(encoding="utf-8").splitlines():
                entry = parse_json_object(line)
                message = entry.get("message")
                if isinstance(message, dict):
                    models.append(message.get("model"))
                efforts.append(entry.get("effort"))
        return RunObservation(models=distinct(models, ignore={"<synthetic>"}), efforts=distinct(efforts))
