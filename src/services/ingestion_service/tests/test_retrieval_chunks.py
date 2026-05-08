from pathlib import Path

from git import Actor, Repo

from app.infra.treesitter_client import TreeSitterManager
from app.retrieval.chunks import build_code_chunks, deterministic_chunk_id
from app.worker.artifact_pipeline import build_index_analysis_artifacts


def test_build_code_chunks_is_deterministic_and_links_go_symbols(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

// New builds the service.
func New() Service {
    return Service{}
}

type Service struct{}
""",
    )
    _write_text(
        tmp_path / "README.md",
        """# Acme Project

This repository contains a tiny service.
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)
    metadata = _metadata(tmp_path, repo)
    artifact_result = build_index_analysis_artifacts(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        treesitter=TreeSitterManager(),
        report_progress=lambda *args, **kwargs: None,
        ensure_alive=lambda: None,
    )

    result_one = build_code_chunks(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        artifacts=artifact_result.artifacts,
    )
    result_two = build_code_chunks(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        artifacts=artifact_result.artifacts,
    )

    assert [chunk.chunk_id for chunk in result_one.chunks] == [
        chunk.chunk_id for chunk in result_two.chunks
    ]
    assert result_one.stats["chunks_total"] == 4
    assert result_one.stats["by_chunk_kind"] == {"file_slice": 2, "go_symbol": 2}
    assert result_one.stats["skipped_files"] == {"represented_by_go_symbols": 1}

    chunks_by_name = {chunk.payload.get("name"): chunk for chunk in result_one.chunks}
    new_chunk = chunks_by_name["service.New"]
    assert new_chunk.payload["chunk_kind"] == "go_symbol"
    assert new_chunk.payload["symbol_id"] in result_one.symbol_chunk_map
    assert result_one.symbol_chunk_map[new_chunk.payload["symbol_id"]] == (new_chunk.chunk_id,)
    assert new_chunk.payload["package_id"] == "github.com/acme/project/internal/service#service"
    assert new_chunk.payload["workspace_unit_id"] == "backend:root"
    assert new_chunk.payload["start_line"] == 4
    assert "Signature: func New() Service" in new_chunk.text
    assert "Doc: New builds the service." in new_chunk.text

    readme_chunk = chunks_by_name["README.md"]
    assert readme_chunk.payload["chunk_kind"] == "file_slice"
    assert readme_chunk.payload["language"] == "markdown"
    assert readme_chunk.payload["source_scope"] == "docs"


def test_deterministic_chunk_ids_change_by_snapshot() -> None:
    chunk_id = deterministic_chunk_id(
        snapshot_id="snapshot-a",
        file_path="internal/service.go",
        symbol_signature="func New() Service",
        chunk_index=0,
    )
    same_chunk_id = deterministic_chunk_id(
        snapshot_id="snapshot-a",
        file_path="./internal/service.go",
        symbol_signature="func New() Service",
        chunk_index=0,
    )
    other_snapshot_chunk_id = deterministic_chunk_id(
        snapshot_id="snapshot-b",
        file_path="internal/service.go",
        symbol_signature="func New() Service",
        chunk_index=0,
    )

    assert chunk_id == same_chunk_id
    assert chunk_id != other_snapshot_chunk_id


def _metadata(repo_root: Path, repo: Repo) -> dict[str, object]:
    commit = repo.head.commit
    files = [path for path in repo_root.rglob("*") if path.is_file() and ".git" not in path.parts]
    return {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "files_total": len(files),
        "go_files_total": sum(1 for path in files if path.suffix == ".go"),
        "readme_files_total": sum(1 for path in files if path.name.lower().startswith("readme")),
        "bytes_total": sum(path.stat().st_size for path in files),
    }


def _commit_all(repo: Repo, repo_root: Path) -> None:
    paths = [
        str(path.relative_to(repo_root))
        for path in sorted(repo_root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    ]
    repo.index.add(paths)
    actor = Actor("DopDoc", "dopdoc@example.com")
    repo.index.commit("init", author=actor, committer=actor)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
