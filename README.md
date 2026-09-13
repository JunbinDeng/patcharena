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

- `0`: every run of every agent finished with status `success`
- `1`: the benchmark ran, but at least one run did not succeed
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
repeat: 1
# hidden_tests: ./hidden_tests
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
- `agents`: Optional list; defaults to `codex` and `claude`. Each entry is either an agent name or a mapping with `agent`, an optional `id` (defaults to the agent name, must be unique, and names the workspace directory), and optional `model` and `effort` (see [Comparing Agents Fairly](#comparing-agents-fairly))
- `agent_timeout`: Optional integer (default `1800`); maximum seconds each agent process may run before it is killed and the result recorded as `error`
- `validation_timeout`: Optional integer (default `600`); maximum seconds each of `compile_command` and `test_command` may run before it is killed and counted as failed
- `repeat`: Optional integer (default `1`); number of times each agent runs the task, each time in a fresh workspace. Runs of one agent happen one after another; different agents run in parallel
- `hidden_tests`: Optional directory outside `repo_path`. After an agent finishes and its patch is saved, the directory's contents are copied over the workspace and validation runs. Agents never see these files, and any same-path file an agent edited is restored first, so an agent cannot pass by weakening the tests

`repo_path` and `hidden_tests` may be relative to the location of `task.yaml`.

How `repo_path` becomes a workspace:

- **Root of a git repository**: cloned, so only committed changes are included.
  PatchArena warns when the repository has uncommitted changes and records this
  in the report as `source_has_uncommitted_changes`.
- **Subdirectory of a git repository**: the committed contents of that
  subdirectory are checked out into a fresh repository.
- **Any other directory**: copied as-is into a fresh repository.

## Comparing Agents Fairly

Unless told otherwise, each agent CLI uses its own default model and reasoning
effort from your global configuration, so a plain run compares combinations of
agent and model. Pin both per entry to compare like with like:

```yaml
agents:
  - {id: claude-sonnet, agent: claude, model: claude-sonnet-5, effort: high}
  - {id: copilot-sonnet, agent: copilot, model: claude-sonnet-5, effort: high}
  - {id: opencode-sonnet, agent: opencode, model: github-copilot/claude-sonnet-5, effort: high}
  - {id: codex-luna, agent: codex, model: gpt-5.6-luna, effort: high}
  - {id: copilot-luna, agent: copilot, model: gpt-5.6-luna, effort: high}
  - {id: opencode-luna, agent: opencode, model: github-copilot/gpt-5.6-luna, effort: high}
```

`model` and `effort` are passed as each CLI's own flags; valid values differ between CLIs:

| agent | `model` | `effort` |
|---|---|---|
| claude | `--model` | `--effort` |
| codex | `--model` | `-c model_reasoning_effort="..."` |
| copilot | `--model` | `--effort` |
| opencode | `--model` (`provider/model`) | `--variant` |

No model is available in every CLI, so compare within groups that share one:
Claude models run in claude, copilot, and opencode; GPT models in codex,
copilot, and opencode. What you can actually use depends on your subscriptions:
a CLI may list a model that your account or plan cannot use, in which case the
run fails or reports `settings_check: unverified`.

A CLI accepting a flag does not prove the setting took effect. After every run,
PatchArena reads the model and effort the CLI itself recorded and reports them
as `observed_model` and `observed_effort`:

- codex: the configuration header printed by `codex exec`
- claude: the session transcript under `~/.claude/projects/`
- copilot: the session events under `~/.copilot/session-state/`
- opencode: the session messages in `~/.local/share/opencode/opencode.db`

`settings_check` is then `verified` (the recorded values are exactly the pinned
ones), `mismatch`, `unverified` (the CLI recorded nothing for a pinned setting),
or `not_pinned`. PatchArena warns about `mismatch` and `unverified` runs.
`model: auto` (supported by copilot) lets the CLI choose a model: the choice is
still reported as `observed_model`, but there is nothing to verify it against. These
records are internal files of each CLI and may change between versions.

## Output Layout

PatchArena writes results under:

```text
runs/
  <task-name>/
    benchmark_report.json
    codex/
      run-1/
        PATCHARENA_TASK.md
        fix.patch
        ...
      run-2/
        ...
    claude/
      run-1/
        ...
    opencode/
      run-1/
        ...
    copilot/
      run-1/
        ...
```

Each run of each agent gets its own workspace directory.

## Report Shape

The JSON report contains:

- top-level task metadata, including `repeat`, `hidden_tests`, and
  `source_has_uncommitted_changes`
- an `agents` list with one summary per agent
- a `results` list with one entry per run of each agent

Each agent summary includes:

- `id`, `agent`, `model`, `effort`
- `runs`
- `successful_runs`
- `pass_at_k`: for every k from 1 to `repeat`, the estimated probability that at
  least one of k runs succeeds (the unbiased estimator from the Codex paper);
  `pass_at_k["1"]` is the success rate
- `status_counts`
- `settings_checks`: how many runs got each `settings_check` value
- `mean_runtime_seconds`
- `mean_patch_lines`

Each result includes:

- `id`, `agent`, `model`, `effort`
- `run`
- `runtime_seconds`
- `patch_lines`
- `files_changed`
- `insertions`
- `deletions`
- `compile_passed`
- `tests_passed`
- `status`
- `observed_model`, `observed_effort`, `settings_check`
- `agent_exit_code`
- `agent_command`
- `agent_stdout`
- `agent_stderr`
- `agent_errors`: errors the agent CLI recorded even though it exited with status 0
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
- `agent_failed`: the agent CLI exited with a non-zero status, or recorded
  errors (`agent_errors`) despite exiting with 0, as opencode does when its
  requests fail
- `error`

PatchArena does not currently expose per-agent output settings in `task.yaml`
or the CLI. Agent CLIs may still have their own output controls; for example,
the locally installed `claude` CLI advertises `--output-format` and
`--debug-file`. PatchArena simply captures whatever the agent process emits to
stdout and stderr and stores those as `agent_stdout` and `agent_stderr` in the
report.

## How It Works

1. Load `task.yaml`
2. Clone or copy the source into one workspace per agent run
3. Write `PATCHARENA_TASK.md` into each workspace; each agent injects its own files via `setup_workspace()`
4. Run agents in parallel; the `repeat` runs of one agent happen one after another
5. Save `fix.patch` using `git diff`, before validation, so build and test artifacts stay out of it
6. Copy `hidden_tests` over the workspace, then run optional compile and test commands
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
- Without `hidden_tests`, validation uses the tests in the agent's own
  workspace, so an agent that edits them can influence its own result
- Agents run in parallel on one machine, so `runtime_seconds` includes
  contention between agents
