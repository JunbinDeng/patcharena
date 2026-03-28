# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run tests
uv run python -m unittest discover -s tests

# Run a single test class or method
uv run python -m unittest tests.test_patcharena.TaskConfigTests
uv run python -m unittest tests.test_patcharena.TaskConfigTests.test_from_file_applies_defaults

# Run the CLI
uv run patcharena run task.yaml
uv run patcharena --help
```

## Architecture

PatchArena is a benchmarking tool that runs multiple AI coding agents (Claude, Claude Bedrock, Codex, OpenCode, Copilot) on the same task in parallel isolated workspaces and generates comparative JSON reports.

### Data Flow

1. **CLI** (`cli.py`) parses `task.yaml` → calls `runner.run_task_file()`
2. **Runner** (`runner.py`) validates agents, spawns `ThreadPoolExecutor` to run `_run_agent_benchmark()` per agent
3. **WorkspaceManager** (`workspace.py`) creates isolated git clones under `runs/<task-name>/<agent>/`, writes `PATCHARENA_TASK.md` (rendered from `templates/PATCHARENA_TASK.md.template`) and `AGENTS.md`
4. Each agent's `setup_workspace()` hook runs to inject agent-specific files (e.g. Claude writes `.claude/settings.json`); then the agent CLI is invoked; optional compile/test commands validate the result
5. **Patch extraction** (`patch.py`) runs `git diff --binary` (excluding task/agent files) and `git diff --shortstat`
6. **Report** (`report.py`) writes `runs/<task-name>/benchmark_report.json`

### Key Models (`models.py`)

- `TaskConfig` — loaded from YAML; fields: `name`, `repo_path`, `prompt`, `compile_command`, `test_command`, `agents`, `agent_timeout`, `agent_options`
- `AgentRunResult` — per-agent outcome: status, timing, patch stats, stdout/stderr, exit codes
- `BenchmarkReport` — aggregates all `AgentRunResult`s with summary statistics

### Agent System (`patcharena/agents/`)

All agents extend `BaseAgent` and implement:
- `build_command(prompt, workspace) -> list[str]` — constructs the subprocess command
- `setup_workspace(workspace) -> list[str]` *(optional)* — injects agent-specific files; returns paths to exclude from the patch
- `extra_env() -> dict[str, str | None]` *(optional)* — per-agent subprocess environment overrides; a `None` value explicitly unsets the key from the inherited environment

Provider routing for the `claude` binary is controlled entirely via `extra_env()`: `ClaudeAgent` unsets `CLAUDE_CODE_USE_BEDROCK` (guaranteeing the Anthropic subscription API even if the key is set in the parent shell), while `ClaudeBedrockAgent` sets it to `"1"`. This ensures the two agents are fully isolated in a side-by-side run.

The agent registry is in `agents/__init__.py`; `get_agent_registry(agent_options)` accepts per-agent options from `TaskConfig`.

| Agent | Binary | Prompt delivery | Notes |
|-------|--------|-----------------|-------|
| claude | `claude` | CLI arg | Anthropic subscription; always unsets `CLAUDE_CODE_USE_BEDROCK` |
| claude-bedrock | `claude` | CLI arg | AWS Bedrock; sets `CLAUDE_CODE_USE_BEDROCK=1`; optional `model` (CLI arg) and `region` (`AWS_REGION` env var) via `agent_options` |
| codex | `codex` | stdin | |
| opencode | `opencode` | CLI arg | |
| copilot | `copilot` | CLI arg | |

### Git Environment (`git_env.py`)

`configure_process_git_environment()` is called at package import and disables GPG signing for all git subprocesses via `GIT_CONFIG_KEY_N` / `GIT_CONFIG_VALUE_N` environment variables.

### Task YAML Schema

```yaml
name: string               # single path component, no / or ..
repo_path: string          # path to the directory to benchmark against (git repo or plain dir)
prompt: string             # task instructions for agents
compile_command: string    # optional validation command
test_command: string       # optional validation command
agents: [codex, claude]    # default; also supports claude-bedrock, opencode, copilot; no duplicates
agent_timeout: 1800        # seconds before agent process is killed (default: 1800)
agent_options:             # optional per-agent config (currently used by claude-bedrock)
  claude-bedrock:
    model: anthropic.claude-3-5-sonnet-20241022-v2:0  # optional; find IDs via: aws bedrock list-foundation-models --by-provider anthropic
    region: us-east-1                                  # optional; omit to use AWS_REGION / AWS_DEFAULT_REGION env vars
```

### Status Values

`success` | `validation_failed` | `agent_failed` | `error`
