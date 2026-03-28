# PatchArena

PatchArena is a small Python benchmark runner for coding agents.

It creates an isolated git workspace per agent, runs each agent against the
same task, executes optional validation commands, extracts a patch with
`git diff`, and writes a JSON benchmark report.

Current MVP support:

- Codex
- Claude (Anthropic subscription)
- Claude Bedrock (AWS Bedrock)
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
agents:
  - codex
  - claude
  - claude-bedrock
  - opencode
  - copilot
agent_options:
  claude-bedrock:
    model: anthropic.claude-3-5-sonnet-20241022-v2:0  # optional; find IDs via: aws bedrock list-foundation-models --by-provider anthropic
    region: us-east-1                                  # optional
```

Fields:

- `name`: Run name used under `runs/<name>/`; must be a single path component (no `/` or `..`)
- `repo_path`: Local path to a directory (git repository or plain directory)
- `prompt`: Task instructions given to each agent
- `compile_command`: Optional shell command; skipped when empty
- `test_command`: Optional shell command; skipped when empty
- `agents`: Optional list of agents (no duplicates); defaults to `codex` and `claude`; also supports `claude-bedrock`, `opencode`, `copilot`
- `agent_timeout`: Optional integer (default `1800`); maximum seconds each agent process may run before it is killed and the result recorded as `error`
- `agent_options`: Optional per-agent configuration map. Currently used by `claude-bedrock`:
  - `model`: Bedrock model ID; find available IDs with `aws bedrock list-foundation-models --by-provider anthropic`; omit to let the CLI choose
  - `region`: AWS region (e.g. `us-east-1`); omit to rely on `AWS_REGION` / `AWS_DEFAULT_REGION` environment variables

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
    claude-bedrock/
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

Each workspace is created by cloning the source repository (or copying and
initializing a git repo for plain directories) into a separate directory for
that agent.

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
- `agent_command` — full command string including any env var overrides (e.g. `CLAUDE_CODE_USE_BEDROCK=1 claude -p ...`)
- `agent_stdout`
- `agent_stderr`
- `compile_exit_code`
- `compile_command`
- `compile_stderr`
- `test_exit_code`
- `test_command`
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
