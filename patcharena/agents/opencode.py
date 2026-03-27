"""OpenCode agent adapter."""

from __future__ import annotations

import json
from pathlib import Path

from patcharena.agents.base import BaseAgent


class OpenCodeAgent(BaseAgent):
    name = "opencode"
    binary_name = "opencode"

    def setup_workspace(self, workspace: Path) -> list[str]:
        config = {
            "permission": {
                "edit": "allow",
                "bash": "allow",
                "external_directory": "allow",
            }
        }
        (workspace / "opencode.json").write_text(
            json.dumps(config, indent=2) + "\n",
            encoding="utf-8",
        )
        return ["opencode.json"]

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return ["opencode", "run", "--dir", str(workspace), prompt]
