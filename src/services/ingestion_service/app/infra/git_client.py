import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import rmtree

from git import Repo


class RepoCloneError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloneResult:
    path: Path


class GitClient:
    """
    Thin wrapper around GitPython to make cloning testable/mocked and to keep
    git-specific details out of the HTTP layer.
    """

    def clone(self, repo_url: str, branch: str | None = None, clone_root: Path | None = None) -> Path:
        temp_dir = None
        try:
            if clone_root is not None:
                clone_root.mkdir(parents=True, exist_ok=True)

            temp_dir = Path(tempfile.mkdtemp(prefix="repo_", dir=clone_root))
            if branch:
                Repo.clone_from(repo_url, temp_dir, branch=branch)
            else:
                Repo.clone_from(repo_url, temp_dir)
            return temp_dir
        except Exception as e:
            if temp_dir is not None:
                rmtree(temp_dir, ignore_errors=True)

            # keep error message, but wrap it for domain-level handling
            raise RepoCloneError(f"Failed to clone repo {repo_url!r}: {e}") from e
