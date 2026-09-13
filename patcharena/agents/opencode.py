"""OpenCode agent adapter."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from patcharena.agents.base import BaseAgent, distinct, flag, parse_json_object
from patcharena.models import CommandResult, RunObservation


class OpenCodeAgent(BaseAgent):
    binary_name = "opencode"

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return [
            "opencode",
            "run",
            "--dir",
            str(workspace),
            *flag("--model", self.model),
            *flag("--variant", self.effort),
            prompt,
        ]

    def observe_run(self, workspace: Path, started_at: float, result: CommandResult) -> RunObservation:
        del result
        # Assistant messages name the provider, model, and variant that answered. `opencode run` exits
        # with status 0 even when a request fails; such a message carries an `error` instead, and proves
        # nothing about the settings in effect.
        models: list[object] = []
        efforts: list[object] = []
        errors: list[object] = []
        for message in _assistant_messages(workspace, started_at):
            error = message.get("error")
            if isinstance(error, dict):
                data = error.get("data")
                errors.append((data.get("message") if isinstance(data, dict) else None) or error.get("name"))
            elif error:
                errors.append(str(error))
            else:
                provider, model = message.get("providerID"), message.get("modelID")
                if provider and model:
                    models.append(f"{provider}/{model}")
                efforts.append(message.get("variant"))
        return RunObservation(models=distinct(models), efforts=distinct(efforts), errors=distinct(errors))


def _assistant_messages(workspace: Path, started_at: float) -> list[dict[str, Any]]:
    """Return the assistant messages of OpenCode sessions in ``workspace`` created since ``started_at``."""
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    database = data_home / "opencode" / "opencode.db"
    if not database.exists():
        return []
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select m.data from session s join message m on m.session_id = s.id"
            " where s.directory = ? and s.time_created >= ? order by m.time_created",
            (str(workspace.resolve()), int(started_at * 1000)),
        ).fetchall()
    finally:
        connection.close()
    messages = [parse_json_object(data) for (data,) in rows]
    return [message for message in messages if message.get("role") == "assistant"]
