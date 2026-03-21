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

PatchArena is a benchmarking tool that runs multiple AI coding agents (Claude, Codex, OpenCode, Copilot) on the same task in parallel isolated workspaces and generates comparative JSON reports.

### Data Flow

1. **CLI** (`cli.py`) parses `task.yaml` → calls `runner.run_task_file()`
2. **Runner** (`runner.py`) validates agents, spawns `ThreadPoolExecutor` to run `_run_agent_benchmark()` per agent
3. **WorkspaceManager** (`workspace.py`) creates isolated git clones under `runs/<task-name>/<agent>/`, writes `PATCHARENA_TASK.md` (rendered from `templates/PATCHARENA_TASK.md.template`) and `AGENTS.md`
4. Each agent's CLI is invoked in its workspace; optional compile/test commands validate the result
5. **Patch extraction** (`patch.py`) runs `git diff --binary` (excluding task/agent files) and `git diff --shortstat`
6. **Report** (`report.py`) writes `runs/<task-name>/benchmark_report.json`

### Key Models (`models.py`)

- `TaskConfig` — loaded from YAML; fields: `name`, `repo_path`, `prompt`, `compile_command`, `test_command`, `agents`, `patch_only`, `agent_timeout`
- `AgentRunResult` — per-agent outcome: status, timing, patch stats, stdout/stderr, exit codes
- `BenchmarkReport` — aggregates all `AgentRunResult`s with summary statistics

### Agent System (`patcharena/agents/`)

All agents extend `BaseAgent` and implement `build_command(task, workspace) -> list[str]`. The agent registry is a dict in `runner.py` mapping name strings to agent classes.

| Agent | Binary | Prompt delivery |
|-------|--------|-----------------|
| claude | `claude` | CLI arg |
| codex | `codex` | stdin |
| opencode | `opencode` | CLI arg |
| copilot | `copilot` | CLI arg |

`patch_only=true` in the task config restricts agents to file edits only (Claude uses `acceptEdits` permission mode; others receive guidance via `AGENTS.md`).

### Git Environment (`git_env.py`)

`configure_process_git_environment()` is called at package import and disables GPG signing for all git subprocesses via `GIT_CONFIG_KEY_N` / `GIT_CONFIG_VALUE_N` environment variables.

### Task YAML Schema

```yaml
name: string               # single path component, no / or ..
repo_path: string          # path to the directory to benchmark against (git repo or plain dir)
prompt: string             # task instructions for agents
compile_command: string    # optional validation command
test_command: string       # optional validation command
agents: [codex, claude]    # default; also supports opencode, copilot; no duplicates
patch_only: false          # restrict agents to file edits only
agent_timeout: 1800        # seconds before agent process is killed (default: 1800)
```

### Status Values

`success` | `validation_failed` | `agent_failed` | `error`
