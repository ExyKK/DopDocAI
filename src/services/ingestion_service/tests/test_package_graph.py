import json
from pathlib import Path

from git import Actor, Repo

from app.artifacts.go_symbols import build_go_symbols_artifact
from app.artifacts.package_graph import build_package_graph_artifact


def test_build_package_graph_artifact_is_deterministic_and_maps_go_imports(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
toolchain go1.22.1
""",
    )
    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import (
    "context"
    "github.com/acme/project/internal/service"
    "github.com/acme/project/pkg/config"
    "github.com/rs/zerolog/log"
)

func main() {
    _ = context.Background()
    _ = config.Load()
    _ = service.New()
    log.Info().Msg("ready")
}
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

import (
    "database/sql"
    "github.com/acme/project/pkg/config"
)

func New() *Service {
    _ = sql.ErrNoRows
    _ = config.Load()
    return &Service{}
}

type Service struct{}
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service_test.go",
        """package service_test

import (
    "testing"
    "github.com/acme/project/internal/service"
)

func TestNew(t *testing.T) {
    _ = service.New()
}
""",
    )
    _write_text(
        tmp_path / "pkg" / "config" / "config.go",
        """package config

type Config struct{}

func Load() Config {
    return Config{}
}
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)

    commit = repo.head.commit
    metadata = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "go_files_total": 4,
        "readme_files_total": 0,
        "bytes_total": sum(
            path.stat().st_size
            for path in tmp_path.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }

    go_symbols = build_go_symbols_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )
    artifact_one = build_package_graph_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        go_symbols_artifact=go_symbols,
    )
    artifact_two = build_package_graph_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        go_symbols_artifact=go_symbols,
    )

    assert artifact_one.payload == artifact_two.payload
    assert artifact_one.checksum_sha256 == artifact_two.checksum_sha256
    assert artifact_one.artifact_kind == "package_graph"
    assert artifact_one.schema_version == 1
    assert artifact_one.row_count == 4
    assert artifact_one.storage_key.endswith("/analysis/package_graph.schema-v1.json")

    document = json.loads(artifact_one.payload.decode("utf-8"))

    assert document["module"] == {
        "go_mod_path": "go.mod",
        "go_version": "1.22",
        "path": "github.com/acme/project",
        "toolchain": "go1.22.1",
    }
    assert document["summary"] == {
        "cgo_edges_total": 0,
        "edge_kind_counts": {
            "external": 1,
            "internal": 4,
            "standard_library": 3,
        },
        "edges_total": 8,
        "entrypoint_packages_total": 1,
        "external_edges_total": 1,
        "files_without_package_total": 0,
        "go_files_total": 4,
        "internal_edges_total": 4,
        "packages_total": 4,
        "standard_library_edges_total": 3,
        "vendor_edges_total": 0,
    }

    packages_by_key = {(package["dir_path"], package["name"]): package for package in document["packages"]}
    cmd_api = packages_by_key[("cmd/api", "main")]
    service = packages_by_key[("internal/service", "service")]
    service_test = packages_by_key[("internal/service", "service_test")]
    config = packages_by_key[("pkg/config", "config")]

    assert cmd_api["is_entrypoint"] is True
    assert cmd_api["entrypoint_kind"] == "cmd"
    assert cmd_api["import_path"] == "github.com/acme/project/cmd/api"
    assert cmd_api["internal_imports"] == [
        "github.com/acme/project/internal/service",
        "github.com/acme/project/pkg/config",
    ]
    assert cmd_api["standard_library_imports"] == ["context"]
    assert cmd_api["external_imports"] == ["github.com/rs/zerolog/log"]

    assert service["package_id"] == "github.com/acme/project/internal/service#service"
    assert service_test["package_id"] == "github.com/acme/project/internal/service#service_test"
    assert service_test["is_test_package"] is True
    assert service_test["internal_imports"] == ["github.com/acme/project/internal/service"]
    assert config["imports"] == []

    assert document["entrypoints"] == [
        {
            "dir_path": "cmd/api",
            "entrypoint_kind": "cmd",
            "files": ["cmd/api/main.go"],
            "import_path": "github.com/acme/project/cmd/api",
            "name": "main",
            "package_id": "github.com/acme/project/cmd/api#main",
        }
    ]

    edges_by_key = {
        (edge["from_package_id"], edge["import_path"]): edge for edge in document["edges"]
    }
    main_to_service = edges_by_key[
        ("github.com/acme/project/cmd/api#main", "github.com/acme/project/internal/service")
    ]
    assert main_to_service["kind"] == "internal"
    assert main_to_service["to_package_id"] == "github.com/acme/project/internal/service#service"
    assert main_to_service["to_dir_path"] == "internal/service"
    assert main_to_service["files"] == ["cmd/api/main.go"]

    service_to_config = edges_by_key[
        ("github.com/acme/project/internal/service#service", "github.com/acme/project/pkg/config")
    ]
    assert service_to_config["kind"] == "internal"
    assert service_to_config["to_package_id"] == "github.com/acme/project/pkg/config#config"

    assert edges_by_key[("github.com/acme/project/cmd/api#main", "context")]["kind"] == "standard_library"
    assert (
        edges_by_key[("github.com/acme/project/cmd/api#main", "github.com/rs/zerolog/log")]["kind"]
        == "external"
    )


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
