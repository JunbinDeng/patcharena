"""Claude Bedrock agent adapter."""

from __future__ import annotations

from pathlib import Path

from patcharena.agents.claude import ClaudeAgent


class ClaudeBedrockAgent(ClaudeAgent):
    name = "claude-bedrock"
    binary_name = "claude"

    def __init__(self, model: str = "", region: str = "") -> None:
        if model and not isinstance(model, str):
            raise ValueError(f"claude-bedrock 'model' must be a string, got {type(model).__name__!r}")
        if region and not isinstance(region, str):
            raise ValueError(f"claude-bedrock 'region' must be a string, got {type(region).__name__!r}")
        self.model = model
        self.region = region

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        del workspace
        cmd = ["claude", "-p", prompt]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def extra_env(self) -> dict[str, str | None]:
        env: dict[str, str] = {"CLAUDE_CODE_USE_BEDROCK": "1"}
        if self.region:
            env["AWS_REGION"] = self.region
        return env
