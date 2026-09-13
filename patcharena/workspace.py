"""Workspace preparation for agent runs."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from string import Template

from patcharena.git_env import git_environment
from patcharena.models import TaskConfig


@dataclass(slots=True)
class PreparedWorkspace:
    """Filesystem paths for a prepared workspace."""

    path: Path
    task_file: Path
    patch_file: Path
    excluded_patch_paths: list[str]


class WorkspaceManager:
    """Creates a separate git workspace for each agent run."""

    def __init__(self, runs_root: Path, templates_dir: Path | None = None) -> None:
        self.runs_root = Path(runs_root)
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent.parent / "templates"
        self.templates_dir = Path(templates_dir)

    def run_dir(self, task_name: str) -> Path:
        return self.runs_root / task_name

    def workspace_dir(self, task_name: str, agent_name: str, run_index: int) -> Path:
        return self.run_dir(task_name) / agent_name / f"run-{run_index}"

    def task_path(self, task_name: str, agent_name: str, run_index: int) -> Path:
        return self.workspace_dir(task_name, agent_name, run_index) / "PATCHARENA_TASK.md"

    def patch_path(self, task_name: str, agent_name: str, run_index: int) -> Path:
        return self.workspace_dir(task_name, agent_name, run_index) / "fix.patch"

    def prepare(self, task: TaskConfig, agent_name: str, run_index: int) -> PreparedWorkspace:
        source = self.validate_source(task.repo_path)
        workspace = self.workspace_dir(task.name, agent_name, run_index)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        _remove_path(workspace)

        toplevel = _committed_toplevel(source)
        if toplevel == source:
            _git_clone(source, workspace)
        else:
            if toplevel is None:
                shutil.copytree(source, workspace)
            else:
                _export_committed_subdirectory(toplevel, source, workspace)
            _commit_snapshot(workspace)

        excluded_paths = ["PATCHARENA_TASK.md"]
        self.task_path(task.name, agent_name, run_index).write_text(
            self.render_task_markdown(task),
            encoding="utf-8",
        )

        agents_file = workspace / "AGENTS.md"
        patcharena_content = self.read_template("AGENTS.md")
        if agents_file.exists():
            existing = agents_file.read_text(encoding="utf-8")
            agents_file.write_text(existing.rstrip("\n") + "\n\n" + patcharena_content, encoding="utf-8")
        else:
            agents_file.write_text(patcharena_content, encoding="utf-8")
        excluded_paths.append("AGENTS.md")

        return PreparedWorkspace(
            path=workspace,
            task_file=self.task_path(task.name, agent_name, run_index),
            patch_file=self.patch_path(task.name, agent_name, run_index),
            excluded_patch_paths=excluded_paths,
        )

    def validate_source(self, source_path: Path) -> Path:
        resolved = Path(source_path).resolve()
        if not resolved.is_dir():
            raise ValueError(f"source path does not exist or is not a directory: {resolved}")
        return resolved

    def render_task_markdown(self, task: TaskConfig) -> str:
        template = Template(self.read_template("PATCHARENA_TASK.md.template"))
        return template.safe_substitute(
            name=task.name,
            repo_path=str(task.repo_path),
            prompt=task.prompt,
            compile_command=task.compile_command or "(skipped)",
            test_command=task.test_command or "(skipped)",
        )

    def read_template(self, template_name: str) -> str:
        return (self.templates_dir / template_name).read_text(encoding="utf-8")


def has_uncommitted_changes(source_path: Path) -> bool:
    """Return whether a git-backed source has changes its workspaces will not contain."""
    source = Path(source_path).resolve()
    if not source.is_dir() or _committed_toplevel(source) is None:
        return False
    status = _git(["status", "--porcelain", "--", "."], cwd=source)
    return status.returncode == 0 and bool(status.stdout.strip())


def _committed_toplevel(source: Path) -> Path | None:
    """Return the git toplevel when ``source`` is a repository root or a committed directory inside one."""
    result = _git(["rev-parse", "--show-toplevel"], cwd=source)
    if result.returncode != 0:
        return None
    toplevel = Path(result.stdout.strip()).resolve()
    if toplevel == source or _git(["cat-file", "-e", _head_tree(toplevel, source)], cwd=toplevel).returncode == 0:
        return toplevel
    return None


def _head_tree(toplevel: Path, directory: Path) -> str:
    return f"HEAD:{directory.relative_to(toplevel).as_posix()}"


def _git_clone(source: Path, workspace: Path) -> None:
    _check_git(["clone", str(source), str(workspace.resolve())])


def _export_committed_subdirectory(toplevel: Path, directory: Path, workspace: Path) -> None:
    """Check out the committed contents of ``directory`` without the rest of the repository."""
    workspace.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as index_dir:
        # A throwaway index keeps the source repository's own index untouched.
        env = git_environment()
        env["GIT_INDEX_FILE"] = str(Path(index_dir) / "index")
        _check_git(["read-tree", _head_tree(toplevel, directory)], cwd=toplevel, env=env)
        _check_git(["checkout-index", "--all", f"--prefix={workspace.resolve()}/"], cwd=toplevel, env=env)


def _commit_snapshot(workspace: Path) -> None:
    for args in [
        ["init"],
        ["add", "-A"],
        ["-c", "user.name=PatchArena", "-c", "user.email=patcharena@example.com",
         "commit", "--allow-empty", "-m", "patcharena: initial snapshot"],
    ]:
        _check_git(args, cwd=workspace)


def _git(
    args: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=git_environment() if env is None else env,
    )


def _check_git(
    args: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    result = _git(args, cwd=cwd, env=env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()
