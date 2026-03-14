# PatchArena

PatchArena is a small Python benchmark runner for coding agents.

It creates an isolated git workspace per agent, runs each agent against the
same task, executes optional validation commands, extracts a patch with
`git diff`, and writes a JSON benchmark report.

Current MVP support:

- Codex
- Claude
- OpenCode
- Copilot
- Local source repositories
- JSON reporting

## Requirements

- Python 3.11+
- `uv`
- `git`
- Agent CLIs installed locally if you want to run them:
  - `codex`
  - `claude`
  - `opencode`
  - `copilot`

## Install and Run

PatchArena is designed to run with `uv`.

Show the CLI:

```bash
uv run patcharena --help
```

Run a benchmark:

```bash
uv run patcharena run task.yaml
```

The command prints the path to the generated report.

## Task File

PatchArena expects a `task.yaml` file with this shape:

```yaml
name: demo-task
repo_path: /absolute/path/to/local/git/repo
prompt: |
  Fix the failing behavior and keep the project runnable.
compile_command: ""
test_command: pytest
agents:
  - codex
  - claude
  - opencode
  - copilot
```

Fields:

- `name`: Run name used under `runs/<name>/`
- `repo_path`: Local path to a git repository
- `prompt`: Task instructions given to each agent
- `compile_command`: Optional shell command; skipped when empty
- `test_command`: Optional shell command; skipped when empty
- `agents`: Optional list of agents; defaults to `codex` and `claude`

`repo_path` may be relative to the location of `task.yaml`.

## Output Layout

PatchArena writes results under:

```text
runs/
  <task-name>/
    benchmark_report.json
    codex/
      PATCHARENA_TASK.md
      fix.patch
      ...
    claude/
      PATCHARENA_TASK.md
      fix.patch
      ...
    opencode/
      PATCHARENA_TASK.md
      fix.patch
      ...
    copilot/
      PATCHARENA_TASK.md
      fix.patch
      ...
```

Each workspace is created by cloning the source repository into a separate
directory for that agent.

## Report Shape

The JSON report contains:

- top-level task metadata
- a `results` list with one entry per agent
- a `summary` block with aggregate metrics

Each agent result includes:

- `agent`
- `runtime_seconds`
- `patch_lines`
- `files_changed`
- `insertions`
- `deletions`
- `compile_passed`
- `tests_passed`
- `status`
- `agent_exit_code`
- `compile_exit_code`
- `test_exit_code`
- `workspace`
- `patch_file`

Status values:

- `success`
- `validation_failed`
- `agent_failed`
- `error`

## How It Works

1. Load `task.yaml`
2. Clone the source repo into one workspace per agent
3. Write `PATCHARENA_TASK.md` into each workspace
4. Run each agent in parallel
5. Run optional compile and test commands
6. Save `fix.patch` using `git diff`
7. Write `benchmark_report.json`

## Development

Run the test suite:

```bash
uv run python -m unittest discover -s tests
```

## MVP Limitations

- Only local repositories are supported
- Reporting is JSON-only
- Real agent execution depends on local CLI auth and setup
