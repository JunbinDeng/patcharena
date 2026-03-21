"""Workspace preparation for agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
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
    """Creates isolated git workspaces for each agent run."""

    def __init__(self, runs_root: Path, templates_dir: Path | None = None) -> None:
        self.runs_root = Path(runs_root)
        if templates_dir is None:
            templates_dir = Path(__file__).resolve().parent.parent / "templates"
        self.templates_dir = Path(templates_dir)

    def run_dir(self, task_name: str) -> Path:
        return self.runs_root / task_name

    def workspace_dir(self, task_name: str, agent_name: str) -> Path:
        return self.run_dir(task_name) / agent_name

    def task_path(self, task_name: str, agent_name: str) -> Path:
        return self.workspace_dir(task_name, agent_name) / "PATCHARENA_TASK.md"

    def patch_path(self, task_name: str, agent_name: str) -> Path:
        return self.workspace_dir(task_name, agent_name) / "fix.patch"

    def prepare(self, task: TaskConfig, agent_name: str, patch_only: bool = False) -> PreparedWorkspace:
        source = self.validate_source(task.repo_path)
        workspace = self.workspace_dir(task.name, agent_name)
        self.run_dir(task.name).mkdir(parents=True, exist_ok=True)
        _remove_path(workspace)

        if _is_git_repo(source):
            _git_clone(source, workspace)
        else:
            _copy_and_init(source, workspace)

        excluded_paths = ["PATCHARENA_TASK.md"]
        self.task_path(task.name, agent_name).write_text(
            self.render_task_markdown(task),
            encoding="utf-8",
        )

        agents_file = workspace / "AGENTS.md"
        patcharena_content = self.read_template("AGENTS.md")
        if patch_only:
            patcharena_content += "- Do not run shell commands or execute code. Only read and write files.\n"
        if agents_file.exists():
            existing = agents_file.read_text(encoding="utf-8")
            agents_file.write_text(existing.rstrip("\n") + "\n\n" + patcharena_content, encoding="utf-8")
        else:
            agents_file.write_text(patcharena_content, encoding="utf-8")
        excluded_paths.append("AGENTS.md")

        return PreparedWorkspace(
            path=workspace,
            task_file=self.task_path(task.name, agent_name),
            patch_file=self.patch_path(task.name, agent_name),
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


def _is_git_repo(path: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        check=False,
        env=git_environment(),
    )
    return result.returncode == 0


def _git_clone(source: Path, workspace: Path) -> None:
    result = subprocess.run(
        ["git", "clone", str(source), str(workspace)],
        text=True,
        capture_output=True,
        check=False,
        env=git_environment(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git clone failed")


def _copy_and_init(source: Path, workspace: Path) -> None:
    shutil.copytree(source, workspace)
    for command in [
        ["git", "init"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=PatchArena", "-c", "user.email=patcharena@example.com",
         "commit", "--allow-empty", "-m", "patcharena: initial snapshot"],
    ]:
        result = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            capture_output=True,
            check=False,
            env=git_environment(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"git {command[1]} failed")


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()
