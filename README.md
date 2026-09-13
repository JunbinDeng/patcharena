# PatchArena

PatchArena is a small Python benchmark runner for coding agents.

It creates a separate git workspace per agent, runs each agent against the
same task, extracts a patch with `git diff`, executes optional validation
commands, and writes a JSON benchmark report.

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

Create a local task file from the sample:

```bash
cp task.example.yaml task.yaml
```

Edit `task.yaml` for your local repository and commands, then run a benchmark:

```bash
uv run patcharena run task.yaml
```

`task.yaml` is intentionally untracked so you can keep machine-specific paths
and private benchmark prompts locally. The command prints the path to the
generated report.

PatchArena refuses to replace the results of an earlier run of the same task.
Pass `--overwrite` to delete them and run again:

```bash
uv run patcharena run task.yaml --overwrite
```

Exit codes:

- `0`: every agent finished with status `success`
- `1`: the benchmark ran, but at least one agent did not succeed
- `2`: the task file is invalid or the run directory already exists
- `130`: interrupted with Ctrl+C

## Task File

PatchArena ships a tracked sample at `task.example.yaml`. Copy it to a local
`task.yaml` and update the values for your environment:

```yaml
name: demo-task
repo_path: /absolute/path/to/local/git/repo
prompt: |
  Fix the failing behavior and keep the project runnable.
compile_command: ""
test_command: pytest
agent_timeout: 1800
validation_timeout: 600
agents:
  - codex
  - claude
  - opencode
  - copilot
```

Fields:

- `name`: Run name used under `runs/<name>/`; must be a single path component (no `/` or `..`)
- `repo_path`: Local path to a directory (git repository, subdirectory of one, or plain directory)
- `prompt`: Task instructions given to each agent
- `compile_command`: Optional shell command; skipped when empty
- `test_command`: Optional shell command; skipped when empty
- `agents`: Optional list of agents (no duplicates); defaults to `codex` and `claude`
- `agent_timeout`: Optional integer (default `1800`); maximum seconds each agent process may run before it is killed and the result recorded as `error`
- `validation_timeout`: Optional integer (default `600`); maximum seconds each of `compile_command` and `test_command` may run before it is killed and counted as failed

`repo_path` may be relative to the location of `task.yaml`.

How `repo_path` becomes a workspace:

- **Root of a git repository**: cloned, so only committed changes are included.
  PatchArena warns when the repository has uncommitted changes and records this
  in the report as `source_has_uncommitted_changes`.
- **Subdirectory of a git repository**: the committed contents of that
  subdirectory are checked out into a fresh repository.
- **Any other directory**: copied as-is into a fresh repository.

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

## Report Shape

The JSON report contains:

- top-level task metadata, including `source_has_uncommitted_changes`
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
- `agent_command`
- `agent_stdout`
- `agent_stderr`
- `compile_exit_code`
- `compile_command`
- `compile_stdout`
- `compile_stderr`
- `test_exit_code`
- `test_command`
- `test_stdout`
- `test_stderr`
- `workspace`
- `patch_file`

Status values:

- `success`
- `validation_failed`
- `agent_failed`
- `error`

PatchArena does not currently expose per-agent output settings in `task.yaml`
or the CLI. Agent CLIs may still have their own output controls; for example,
the locally installed `claude` CLI advertises `--output-format` and
`--debug-file`. PatchArena simply captures whatever the agent process emits to
stdout and stderr and stores those as `agent_stdout` and `agent_stderr` in the
report.

## How It Works

1. Load `task.yaml`
2. Clone or copy the source into one workspace per agent
3. Write `PATCHARENA_TASK.md` into each workspace; each agent injects its own files via `setup_workspace()`
4. Run each agent in parallel
5. Save `fix.patch` using `git diff`, before validation, so build and test artifacts stay out of it
6. Run optional compile and test commands
7. Write `benchmark_report.json`

Every agent and validation command runs in its own process group. When it
exits or times out, PatchArena kills the whole group, so background processes
it started cannot keep running or keep changing the workspace.

## Development

Run the test suite, linter, and type checker:

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
uv run mypy
```

## MVP Limitations

- Only local repositories are supported
- Reporting is JSON-only
- Real agent execution depends on local CLI auth and setup
- No sandboxing by PatchArena: workspaces are plain directories, and most agents
  run on the host with broad permissions (for example Claude with
  `--allowedTools Edit,Write,Bash` and Copilot with `--allow-all-tools`; Codex
  uses its own `--sandbox workspace-write`). Run PatchArena inside a container
  or VM for untrusted tasks.
- Validation runs in the agent's own workspace, so an agent that edits the
  tests can influence its own result
- Each agent runs once per task, so results do not account for run-to-run variance
