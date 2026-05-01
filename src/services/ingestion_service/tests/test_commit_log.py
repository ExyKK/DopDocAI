import json
from pathlib import Path

from git import Actor, Repo

from app.artifacts.commit_log import build_commit_log_artifact
from app.artifacts.go_symbols import build_go_symbols_artifact
from app.artifacts.package_graph import build_package_graph_artifact


def test_build_commit_log_artifact_collects_base_to_head_changes(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

func New() string {
    return "v1"
}
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path, "initial")
    base_commit_sha = repo.head.commit.hexsha.lower()

    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

func New() string {
    return "v2"
}
""",
    )
    _commit_all(repo, tmp_path, "update service")

    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import "github.com/acme/project/internal/service"

func main() {
    _ = service.New()
}
""",
    )
    _commit_all(repo, tmp_path, "add api")

    metadata = _snapshot_metadata(tmp_path, repo, base_commit_sha=base_commit_sha)
    package_graph = _build_package_graph(tmp_path, metadata)

    artifact_one = build_commit_log_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        package_graph_artifact=package_graph,
    )
    artifact_two = build_commit_log_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        package_graph_artifact=package_graph,
    )

    assert artifact_one.payload == artifact_two.payload
    assert artifact_one.checksum_sha256 == artifact_two.checksum_sha256
    assert artifact_one.artifact_kind == "commit_log"
    assert artifact_one.schema_version == 1
    assert artifact_one.row_count == 2
    assert artifact_one.storage_key.endswith("/analysis/commit_log.schema-v1.json")

    document = json.loads(artifact_one.payload.decode("utf-8"))
    assert document["range"]["mode"] == "base_to_head"
    assert document["range"]["base_snapshot_id"] == "base-snapshot-id"
    assert document["range"]["base_commit_sha"] == base_commit_sha
    assert document["range"]["base_commit_reachable"] is True
    assert document["range"]["commits_available"] == 2
    assert document["summary"] == {
        "base_commit_reachable": True,
        "change_type_counts": {"added": 1, "modified": 1},
        "commits_available": 2,
        "commits_total": 2,
        "has_base_snapshot": True,
        "max_commits": 50,
        "merge_commits_total": 0,
        "touched_files_total": 2,
        "touched_go_files_total": 2,
        "touched_packages_total": 2,
        "truncated": False,
    }

    assert [commit["subject"] for commit in document["commits"]] == ["add api", "update service"]
    assert [file_record["path"] for file_record in document["touched_files"]] == [
        "cmd/api/main.go",
        "internal/service/service.go",
    ]
    assert {package["dir_path"] for package in document["touched_packages"]} == {
        "cmd/api",
        "internal/service",
    }
    assert document["commits"][0]["touched_files"][0]["packages"] == [
        {
            "dir_path": "cmd/api",
            "import_path": "github.com/acme/project/cmd/api",
            "name": "main",
            "package_id": "github.com/acme/project/cmd/api#main",
        }
    ]


def test_build_commit_log_artifact_limits_recent_history(tmp_path: Path) -> None:
    _write_text(tmp_path / "README.md", "first\n")
    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path, "initial")

    _write_text(tmp_path / "README.md", "second\n")
    _commit_all(repo, tmp_path, "second")

    _write_text(tmp_path / "README.md", "third\n")
    _commit_all(repo, tmp_path, "third")

    artifact = build_commit_log_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=_snapshot_metadata(tmp_path, repo),
        max_commits=1,
    )

    document = json.loads(artifact.payload.decode("utf-8"))
    assert artifact.row_count == 1
    assert document["range"]["mode"] == "recent"
    assert document["range"]["commits_available"] == 3
    assert document["range"]["truncated"] is True
    assert document["summary"]["commits_total"] == 1
    assert document["summary"]["touched_files_total"] == 1
    assert document["commits"][0]["subject"] == "third"


def _build_package_graph(repo_root: Path, metadata: dict[str, object]):
    go_symbols = build_go_symbols_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )
    return build_package_graph_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        go_symbols_artifact=go_symbols,
    )


def _snapshot_metadata(
    repo_root: Path,
    repo: Repo,
    *,
    base_commit_sha: str | None = None,
) -> dict[str, object]:
    commit = repo.head.commit
    metadata: dict[str, object] = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "files_total": sum(1 for path in repo_root.rglob("*") if path.is_file() and ".git" not in path.parts),
        "go_files_total": sum(
            1
            for path in repo_root.rglob("*.go")
            if path.is_file() and ".git" not in path.parts
        ),
        "readme_files_total": sum(
            1
            for path in repo_root.rglob("*")
            if path.is_file() and path.name.lower().startswith("readme") and ".git" not in path.parts
        ),
        "bytes_total": sum(
            path.stat().st_size
            for path in repo_root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }
    if base_commit_sha is not None:
        metadata["base_snapshot_id"] = "base-snapshot-id"
        metadata["base_commit_sha"] = base_commit_sha

    return metadata


def _commit_all(repo: Repo, repo_root: Path, message: str) -> None:
    paths = [
        str(path.relative_to(repo_root))
        for path in sorted(repo_root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    ]
    repo.index.add(paths)
    actor = Actor("DopDoc", "dopdoc@example.com")
    repo.index.commit(message, author=actor, committer=actor)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
