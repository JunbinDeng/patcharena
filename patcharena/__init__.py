"""PatchArena package."""

from patcharena.git_env import configure_process_git_environment

__all__ = ["__version__"]

configure_process_git_environment()

__version__ = "0.1.0"
