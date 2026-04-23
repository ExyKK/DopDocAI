from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from shutil import rmtree
from typing import Any

from git import Repo

from app.infra.git_client import GitClient


@dataclass(frozen=True)
class SnapshotFileCounters:
    files_total: int
    go_files_total: int
    readme_files_total: int
    bytes_total: int


@dataclass(frozen=True)
class HeadTreeFile:
    path: str
    size: int
    object_type: str


@dataclass(frozen=True)
class ResolvedSnapshot:
    repo_path: str
    metadata: dict[str, Any]

    def cleanup(self) -> None:
        rmtree(self.repo_path, ignore_errors=True)


class SnapshotResolver:
    def __init__(self, git_client: GitClient, clone_root):
        self._git = git_client
        self._clone_root = clone_root

    def resolve(self, repo_url: str, selected_branch: str | None) -> ResolvedSnapshot:
        repo_path = self._git.clone(repo_url, selected_branch, self._clone_root)
        repo = Repo(repo_path)

        branch_name = selected_branch or _current_branch_name(repo)
        commit = repo.head.commit
        repo.git.checkout(commit.hexsha)

        counters = _collect_file_counters(repo)
        message = commit.message.strip()
        subject = message.splitlines()[0] if message else None

        metadata = {
            "branch_name": branch_name,
            "commit_sha": commit.hexsha.lower(),
            "tree_hash": commit.tree.hexsha.lower(),
            "commit_subject": _truncate(subject, 512),
            "commit_message": message or None,
            "commit_author_name": _truncate(commit.author.name, 256),
            "commit_author_email": _truncate(commit.author.email, 320),
            "commit_authored_at": _utc_datetime(commit.authored_datetime),
            "commit_committed_at": _utc_datetime(commit.committed_datetime),
            "files_total": counters.files_total,
            "go_files_total": counters.go_files_total,
            "readme_files_total": counters.readme_files_total,
            "bytes_total": counters.bytes_total,
        }

        return ResolvedSnapshot(repo_path=str(repo_path), metadata=metadata)


def _current_branch_name(repo: Repo) -> str:
    try:
        name = repo.active_branch.name
        if name:
            return name
    except TypeError:
        pass

    try:
        name = repo.git.symbolic_ref("--short", "HEAD").strip()
        if name:
            return name
    except Exception:
        pass

    raise RuntimeError("Unable to resolve selected/default branch for cloned repository.")


def _collect_file_counters(repo: Repo) -> SnapshotFileCounters:
    files_total = 0
    go_files_total = 0
    readme_files_total = 0
    bytes_total = 0

    for entry in list_head_tree_files(repo):
        files_total += 1
        bytes_total += entry.size

        lower_path = entry.path.lower()
        if lower_path.endswith(".go"):
            go_files_total += 1

        name = PurePosixPath(entry.path).name.lower()
        if name == "readme" or name.startswith("readme."):
            readme_files_total += 1

    return SnapshotFileCounters(
        files_total=files_total,
        go_files_total=go_files_total,
        readme_files_total=readme_files_total,
        bytes_total=bytes_total,
    )


def list_head_tree_files(repo: Repo) -> list[HeadTreeFile]:
    files: list[HeadTreeFile] = []
    output = repo.git.ls_tree("-r", "-l", "HEAD")
    for line in output.splitlines():
        parsed = _parse_ls_tree_line(line)
        if parsed is None:
            continue

        files.append(parsed)

    return files


def _parse_ls_tree_line(line: str) -> HeadTreeFile | None:
    parts = line.split(maxsplit=4)
    if len(parts) != 5:
        return None

    object_type = parts[1]
    size_text = parts[3]
    path = parts[4]

    try:
        size = int(size_text)
    except ValueError:
        size = 0

    if object_type != "blob":
        return None

    return HeadTreeFile(path=path, size=size, object_type=object_type)


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    return value.astimezone(timezone.utc)


def _truncate(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None

    return value[:max_length]
