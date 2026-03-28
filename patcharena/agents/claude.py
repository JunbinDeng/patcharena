"""Claude agent adapter."""

from __future__ import annotations

import json
from pathlib import Path

from patcharena.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    name = "claude"
    binary_name = "claude"

    def setup_workspace(self, workspace: Path) -> list[str]:
        claude_dir = workspace / ".claude"
        claude_dir.mkdir(exist_ok=True)
        settings = {
            "permissions": {
                "allow": [
                    "Edit(*)",
                    "Write(*)",
                    "Bash(*)",
                ]
            }
        }
        (claude_dir / "settings.json").write_text(
            json.dumps(settings, indent=2) + "\n",
            encoding="utf-8",
        )
        return [".claude/settings.json"]

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        del workspace
        return ["claude", "-p", prompt]

    def extra_env(self) -> dict[str, str | None]:
        # Explicitly unset so a CLAUDE_CODE_USE_BEDROCK=1 in the parent
        # environment doesn't accidentally route this agent through Bedrock.
        return {"CLAUDE_CODE_USE_BEDROCK": None}
