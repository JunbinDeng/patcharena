"""Helpers for running git commands in an isolated environment."""

from __future__ import annotations

import os
from collections.abc import MutableMapping

_GIT_CONFIG_OVERRIDES = (
    ("commit.gpgsign", "false"),
    ("tag.gpgsign", "false"),
)


def configure_process_git_environment() -> None:
    """Apply stable git config overrides to the current process environment."""

    _apply_git_config_overrides(os.environ)


def git_environment() -> dict[str, str]:
    """Return an environment mapping with PatchArena git overrides applied."""

    env = dict(os.environ)
    _apply_git_config_overrides(env)
    return env


def _apply_git_config_overrides(env: MutableMapping[str, str]) -> None:
    count = _git_config_count(env)
    existing_pairs = {
        (
            env.get(f"GIT_CONFIG_KEY_{index}", ""),
            env.get(f"GIT_CONFIG_VALUE_{index}", ""),
        )
        for index in range(count)
    }

    for key, value in _GIT_CONFIG_OVERRIDES:
        if (key, value) in existing_pairs:
            continue
        env[f"GIT_CONFIG_KEY_{count}"] = key
        env[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1

    env["GIT_CONFIG_COUNT"] = str(count)


def _git_config_count(env: MutableMapping[str, str]) -> int:
    try:
        return int(env.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        return 0
