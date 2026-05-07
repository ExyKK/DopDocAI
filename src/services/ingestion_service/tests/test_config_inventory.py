import json
from pathlib import Path

from git import Actor, Repo

from app.artifacts.config_inventory import (
    _MAX_CONFIG_FILE_BYTES,
    _MAX_CONFIG_KEYS_PER_FILE,
    _MAX_CONFIG_NESTING_DEPTH,
    build_config_inventory_artifact,
)
from app.artifacts.file_inventory import build_file_inventory_artifact
from app.artifacts.go_symbols import build_go_symbols_artifact


def test_build_config_inventory_artifact_extracts_go_and_config_file_metadata(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import (
    "flag"
    "os"
)

type AppConfig struct {
    Host string `json:"host" yaml:"host" env:"APP_HOST" default:"localhost"`
    Port int `mapstructure:"port" validate:"required"`
    Token string `envconfig:"APP_TOKEN" required:"true"`
}

func main() {
    addr := flag.String("addr", ":8080", "listen address")
    workers := flag.Int("workers", 4, "worker count")
    token := flag.String("token", "", "required API token")
    _ = addr
    _ = workers
    _ = token
    _ = os.Getenv("APP_ENV")
    if _, ok := os.LookupEnv("DATABASE_URL"); !ok {
        panic("DATABASE_URL required")
    }
}
""",
    )
    _write_text(
        tmp_path / "config" / "app.yaml",
        """server:
  port: 8080
  token: secret-value
feature:
  enabled: true
""",
    )
    _write_text(
        tmp_path / "config" / "settings.json",
        """{"database": {"url": "postgres://example", "password": "secret"}, "debug": false}
""",
    )
    _write_text(
        tmp_path / "config" / "large.json",
        json.dumps({f"key_{index:03d}": index for index in range(300)}, sort_keys=True) + "\n",
    )
    _write_text(
        tmp_path / "config" / "app.toml",
        """[http]
addr = ":9000"
""",
    )
    _write_text(
        tmp_path / ".env.example",
        """APP_ENV=development
DATABASE_URL=postgres://localhost
APP_TOKEN=example-token
""",
    )
    _write_text(
        tmp_path / "docs" / "swagger" / "swagger.json",
        """{
  "swagger": "2.0",
  "info": {"title": "Image Board API", "version": "v1"},
  "paths": {
    "/posts": {
      "get": {"responses": {"200": {"description": "ok"}}},
      "post": {"responses": {"201": {"description": "created"}}}
    }
  },
  "definitions": {"Post": {"type": "object"}}
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
        "go_files_total": 1,
        "readme_files_total": 0,
        "bytes_total": sum(
            path.stat().st_size
            for path in tmp_path.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }
    metadata["files_total"] = len(
        [path for path in tmp_path.rglob("*") if path.is_file() and ".git" not in path.parts]
    )

    file_inventory = build_file_inventory_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )
    go_symbols = build_go_symbols_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )

    artifact_one = build_config_inventory_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
    )
    artifact_two = build_config_inventory_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
    )

    assert artifact_one.payload == artifact_two.payload
    assert artifact_one.checksum_sha256 == artifact_two.checksum_sha256
    assert artifact_one.artifact_kind == "config_inventory"
    assert artifact_one.schema_version == 1
    assert artifact_one.storage_key.endswith("/analysis/config_inventory.schema-v1.json")

    document = json.loads(artifact_one.payload.decode("utf-8"))
    assert document["summary"] == {
        "config_file_format_counts": {
            "dotenv": 1,
            "json": 2,
            "toml": 1,
            "yaml": 1,
        },
        "api_spec_kind_counts": {"swagger": 1},
        "api_specs_total": 1,
        "config_file_keys_total": 266,
        "config_file_parse_limits": {
            "max_file_bytes": _MAX_CONFIG_FILE_BYTES,
            "max_keys_per_file": _MAX_CONFIG_KEYS_PER_FILE,
            "max_nesting_depth": _MAX_CONFIG_NESTING_DEPTH,
        },
        "config_files_total": 5,
        "config_files_truncated_total": 1,
        "config_structs_total": 1,
        "configuration_items_total": 272,
        "data_contract_kind_counts": {},
        "data_contracts_total": 0,
        "dependency_lock_kind_counts": {},
        "dependency_locks_total": 0,
        "dynamic_env_references_total": 0,
        "dynamic_flag_references_total": 0,
        "env_vars_total": 2,
        "flags_total": 3,
        "required_items_total": 4,
        "runtime_config_file_keys_total": 266,
        "runtime_config_structs_total": 1,
        "runtime_configuration_items_total": 272,
        "runtime_env_vars_total": 2,
        "runtime_flags_total": 3,
        "runtime_required_items_total": 4,
        "source_scope_counts": {
            "api_specs": {"generated": 1},
            "config_files": {"runtime": 5},
            "config_structs": {"runtime": 1},
            "data_contracts": {},
            "dependency_locks": {},
            "dynamic_env_references": {},
            "dynamic_flag_references": {},
            "env_vars": {"runtime": 2},
            "flags": {"runtime": 3},
        },
    }
    assert artifact_one.row_count == 272

    env_by_key = {item["key"]: item for item in document["env_vars"]}
    assert env_by_key["APP_ENV"]["required"] is False
    assert env_by_key["APP_ENV"]["source"]["symbol_qualified_name"] == "main.main"
    assert env_by_key["APP_ENV"]["source_scope"] == "runtime"
    assert env_by_key["APP_ENV"]["runtime_scope"] is True
    assert env_by_key["DATABASE_URL"]["required"] is True
    assert env_by_key["DATABASE_URL"]["required_reason"] == "lookup_env_failure_path"

    flags_by_name = {item["name"]: item for item in document["flags"]}
    assert flags_by_name["addr"]["default_value"] == ":8080"
    assert flags_by_name["workers"]["default_value"] == 4
    assert flags_by_name["token"]["required"] is True
    assert flags_by_name["token"]["required_reason"] == "usage_mentions_required"
    assert flags_by_name["token"]["source_scope"] == "runtime"

    config_struct = document["config_structs"][0]
    assert config_struct["name"] == "AppConfig"
    assert config_struct["model_kind"] == "runtime_config"
    assert config_struct["source"]["symbol_qualified_name"] == "main.AppConfig"
    assert config_struct["source_scope"] == "runtime"
    fields_by_name = {item["name"]: item for item in config_struct["fields"]}
    assert fields_by_name["Host"]["default_value"] == "localhost"
    assert fields_by_name["Host"]["config_keys"] == [
        {"key": "APP_HOST", "source": "env"},
        {"key": "host", "source": "json"},
        {"key": "host", "source": "yaml"},
    ]
    assert fields_by_name["Port"]["required"] is True
    assert fields_by_name["Token"]["required"] is True

    config_files_by_path = {item["path"]: item for item in document["config_files"]}
    assert "docs/swagger/swagger.json" not in config_files_by_path
    assert config_files_by_path["config/app.yaml"]["source_scope"] == "runtime"

    yaml_keys = {item["key"]: item for item in config_files_by_path["config/app.yaml"]["keys"]}
    assert yaml_keys["feature.enabled"]["value_kind"] == "bool"
    assert yaml_keys["server.token"]["value_preview"] == "<redacted>"

    json_keys = {item["key"]: item for item in config_files_by_path["config/settings.json"]["keys"]}
    assert json_keys["database.password"]["value_preview"] == "<redacted>"
    assert json_keys["debug"]["value_kind"] == "bool"

    env_keys = {item["key"]: item for item in config_files_by_path[".env.example"]["keys"]}
    assert env_keys["APP_TOKEN"]["value_preview"] == "<redacted>"
    assert env_keys["DATABASE_URL"]["value_preview"] == "postgres://localhost"

    large_config = config_files_by_path["config/large.json"]
    assert large_config["truncated"] is True
    assert large_config["truncation_reason"] == "max_keys_per_file_exceeded"
    assert len(large_config["keys"]) == _MAX_CONFIG_KEYS_PER_FILE

    assert document["api_specs"] == [
        {
            "format": "json",
            "line_count": 11,
            "operations_total": 2,
            "parse_error": False,
            "path": "docs/swagger/swagger.json",
            "paths_total": 1,
            "source": "file_classification",
            "size_bytes": len((tmp_path / "docs" / "swagger" / "swagger.json").read_bytes()),
            "spec_kind": "swagger",
            "spec_version": "2.0",
            "runtime_scope": False,
            "source_scope": "generated",
            "title": "Image Board API",
            "truncated": False,
            "truncation_reason": None,
            "version": "v1",
        }
    ]


def test_build_config_inventory_artifact_tracks_dynamic_env_and_data_contracts(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "main.go",
        """package main

import (
    "flag"
    "os"
)

type RuntimeConfig struct {
    Host string `yaml:"host" default:"localhost"`
}

type LoginRequest struct {
    Email string `json:"email" binding:"required"`
}

type User struct {
    ID string `json:"id" gorm:"primaryKey"`
}

type Claims struct {
    Role string `json:"role"`
}

func getEnv(key string, fallback string) string {
    if value := os.Getenv(key); value != "" {
        return value
    }
    return fallback
}

func main() {
    flagName := "debug"
    _ = os.Getenv(activeHelpEnvVar("cobra"))
    _ = getEnv("PORT", "8080")
    _ = getEnv(flagName, "fallback")
    _ = flag.String(flagName, "", "dynamic flag")
    _ = flag.String("static", "", "static flag")
}
""",
    )

    document = _build_config_inventory_document(tmp_path)

    env_vars = {item["key"]: item for item in document["env_vars"]}
    assert set(env_vars) == {"PORT"}
    assert env_vars["PORT"]["accessor"] == "getEnv"
    assert env_vars["PORT"]["default_value"] == "8080"
    assert env_vars["PORT"]["confidence"] == "medium"

    dynamic_env_refs = {item["expression"]: item for item in document["dynamic_env_references"]}
    assert set(dynamic_env_refs) == {'activeHelpEnvVar("cobra")', "flagName"}
    assert all(item["kind"] == "dynamic_env_reference" for item in dynamic_env_refs.values())

    flags = {item["name"]: item for item in document["flags"]}
    assert set(flags) == {"static"}
    assert document["dynamic_flag_references"][0]["expression"] == "flagName"

    config_structs = {item["name"]: item for item in document["config_structs"]}
    assert set(config_structs) == {"RuntimeConfig"}
    assert config_structs["RuntimeConfig"]["model_kind"] == "runtime_config"

    data_contracts = {item["name"]: item for item in document["data_contracts"]}
    assert data_contracts["LoginRequest"]["model_kind"] == "api_contract"
    assert data_contracts["User"]["model_kind"] == "persistence_model"
    assert data_contracts["Claims"]["model_kind"] == "auth_claims"
    assert document["summary"]["runtime_configuration_items_total"] == 3
    assert document["summary"]["data_contract_kind_counts"] == {
        "api_contract": 1,
        "auth_claims": 1,
        "persistence_model": 1,
    }


def test_build_config_inventory_artifact_parses_yaml_arrays_and_excludes_lockfiles(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / ".github" / "labeler.yml",
        """area/docs:
  - docs/**/*
area/backend:
  - internal/**/*
""",
    )
    _write_text(
        tmp_path / ".github" / "dependabot.yml",
        """version: 2
updates:
  - package-ecosystem: npm
    directory: /frontend
    schedule:
      interval: weekly
  - package-ecosystem: gomod
    directory: /
""",
    )
    _write_text(
        tmp_path / "frontend" / "package-lock.json",
        json.dumps(
            {
                "name": "frontend",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "frontend"},
                    "node_modules/react": {"version": "19.0.0"},
                },
            },
            sort_keys=True,
        )
        + "\n",
    )
    _write_text(
        tmp_path / "go.sum",
        """github.com/pkg/errors v0.9.1 h1:abc
github.com/pkg/errors v0.9.1/go.mod h1:def
""",
    )

    document = _build_config_inventory_document(tmp_path)
    config_files = {item["path"]: item for item in document["config_files"]}
    assert set(config_files) == {".github/dependabot.yml", ".github/labeler.yml"}
    assert "frontend/package-lock.json" not in config_files

    labeler_keys = {item["key"]: item for item in config_files[".github/labeler.yml"]["keys"]}
    assert labeler_keys["area/backend[0]"]["value_preview"] == "internal/**/*"
    assert labeler_keys["area/docs[0]"]["value_preview"] == "docs/**/*"

    dependabot_keys = {item["key"]: item for item in config_files[".github/dependabot.yml"]["keys"]}
    assert dependabot_keys["updates[0].package-ecosystem"]["value_preview"] == "npm"
    assert dependabot_keys["updates[0].schedule.interval"]["value_preview"] == "weekly"
    assert dependabot_keys["updates[1].directory"]["value_preview"] == "/"

    locks = {item["path"]: item for item in document["dependency_locks"]}
    assert locks["frontend/package-lock.json"]["lockfile_kind"] == "npm_package_lock"
    assert locks["frontend/package-lock.json"]["dependencies_total"] == 1
    assert locks["go.sum"]["lockfile_kind"] == "go_sum"
    assert locks["go.sum"]["dependencies_total"] == 1
    assert document["summary"]["dependency_lock_kind_counts"] == {
        "go_sum": 1,
        "npm_package_lock": 1,
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


def _build_config_inventory_document(repo_root: Path) -> dict[str, object]:
    repo = Repo.init(repo_root)
    _commit_all(repo, repo_root)
    commit = repo.head.commit
    metadata = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "go_files_total": sum(
            1
            for path in repo_root.rglob("*.go")
            if path.is_file() and ".git" not in path.parts
        ),
        "readme_files_total": 0,
        "bytes_total": sum(
            path.stat().st_size
            for path in repo_root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }
    metadata["files_total"] = len(
        [path for path in repo_root.rglob("*") if path.is_file() and ".git" not in path.parts]
    )
    file_inventory = build_file_inventory_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )
    go_symbols = build_go_symbols_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
    )
    artifact = build_config_inventory_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
    )
    return json.loads(artifact.payload.decode("utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
