import json
from pathlib import Path

from git import Actor, Repo

from app.artifacts.config_inventory import build_config_inventory_artifact
from app.artifacts.file_inventory import build_file_inventory_artifact
from app.artifacts.go_symbols import build_go_symbols_artifact
from app.artifacts.package_graph import build_package_graph_artifact
from app.artifacts.project_model import build_project_model_artifact


def test_build_project_model_artifact_aggregates_analysis_artifacts(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
require github.com/go-chi/chi/v5 v5.0.0
""",
    )
    _write_text(tmp_path / "README.md", "# Project\n")
    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import (
    "database/sql"
    "net/http"

    "github.com/acme/project/internal/service"
    "github.com/go-chi/chi/v5"
)

func main() {
    r := chi.NewRouter()
    r.Get("/health", service.Health)
    http.ListenAndServe(":8080", r)
    _ = sql.ErrNoRows
}
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

import (
    "net/http"
    "os"
)

type Config struct {
    DatabaseURL string `env:"DATABASE_URL" required:"true"`
}

func Health(w http.ResponseWriter, r *http.Request) {
    _ = os.Getenv("DATABASE_URL")
    w.WriteHeader(http.StatusOK)
}
""",
    )
    _write_text(
        tmp_path / "config" / "app.yaml",
        """server:
  port: 8080
database:
  url: postgres://localhost
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)

    commit = repo.head.commit
    metadata = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "go_files_total": 2,
        "readme_files_total": 1,
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
    package_graph = build_package_graph_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        go_symbols_artifact=go_symbols,
    )
    config_inventory = build_config_inventory_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
    )

    artifact_one = build_project_model_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
        package_graph_artifact=package_graph,
        config_inventory_artifact=config_inventory,
    )
    artifact_two = build_project_model_artifact(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
        package_graph_artifact=package_graph,
        config_inventory_artifact=config_inventory,
    )

    assert artifact_one.payload == artifact_two.payload
    assert artifact_one.checksum_sha256 == artifact_two.checksum_sha256
    assert artifact_one.artifact_kind == "project_model"
    assert artifact_one.schema_version == 2
    assert artifact_one.storage_key.endswith("/analysis/project_model.schema-v2.json")

    document = json.loads(artifact_one.payload.decode("utf-8"))
    assert document["model_kind"] == "compact_project_manifest"
    assert document["summary"]["bytes_total"] > 0
    assert {
        "api_specs_total": document["summary"]["api_specs_total"],
        "config_files_total": document["summary"]["config_files_total"],
        "config_items_total": document["summary"]["config_items_total"],
        "entrypoint_packages_total": document["summary"]["entrypoint_packages_total"],
        "external_integrations_total": document["summary"]["external_integrations_total"],
        "files_total": document["summary"]["files_total"],
        "go_files_total": document["summary"]["go_files_total"],
        "has_generated_code": document["summary"]["has_generated_code"],
        "has_tests": document["summary"]["has_tests"],
        "has_vendor": document["summary"]["has_vendor"],
        "http_routes_total": document["summary"]["http_routes_total"],
        "http_surface_detected": document["summary"]["http_surface_detected"],
        "packages_total": document["summary"]["packages_total"],
        "symbols_total": document["summary"]["symbols_total"],
        "workspace_units_total": document["summary"]["workspace_units_total"],
    } == {
        "api_specs_total": 0,
        "config_files_total": 1,
        "config_items_total": 4,
        "entrypoint_packages_total": 1,
        "external_integrations_total": 3,
        "files_total": 5,
        "go_files_total": 2,
        "has_generated_code": False,
        "has_tests": False,
        "has_vendor": False,
        "http_routes_total": 1,
        "http_surface_detected": True,
        "packages_total": 2,
        "symbols_total": 3,
        "workspace_units_total": 1,
    }
    assert artifact_one.row_count == 1

    assert "module" not in document
    assert "package_topology" not in document
    assert "symbols" not in document
    assert document["go"]["modules"][0]["path"] == "github.com/acme/project"
    assert document["repository_layout"]["kind_counts"] == {
        "config": 1,
        "go": 2,
        "markdown": 1,
        "other": 1,
    }
    assert document["repository_layout"]["top_level_directories"][0]["path"] == "."

    workspace_units = {item["workspace_unit_id"]: item for item in document["workspace_units"]}
    assert set(workspace_units) == {"backend:root"}
    assert workspace_units["backend:root"]["unit_kind"] == "backend"
    assert workspace_units["backend:root"]["languages"] == ["go"]
    assert workspace_units["backend:root"]["file_counts"]["by_owner"] == {
        "backend": 2,
        "docs": 1,
        "shared": 2,
    }

    entrypoints = document["go"]["entrypoints"]
    assert entrypoints == [
        {
            "dir_path": "cmd/api",
            "entrypoint_kind": "cmd",
            "files": ["cmd/api/main.go"],
            "import_path": "github.com/acme/project/cmd/api",
            "name": "main",
            "package_id": "github.com/acme/project/cmd/api#main",
            "workspace_unit_id": "backend:root",
        }
    ]

    package_ids = {item["package_id"] for item in document["go"]["important_packages"]}
    assert package_ids == {
        "github.com/acme/project/cmd/api#main",
        "github.com/acme/project/internal/service#service",
    }
    assert {item["workspace_unit_id"] for item in document["go"]["important_packages"]} == {"backend:root"}

    symbols = {item["qualified_name"]: item for item in document["code_outline"]["important_symbols"]}
    assert symbols["service.Config"]["kind"] == "struct"
    assert symbols["service.Health"]["kind"] == "function"

    env_vars = {item["key"]: item for item in document["configuration"]["env_vars"]}
    assert env_vars["DATABASE_URL"]["source_file_path"] == "internal/service/service.go"
    assert document["configuration"]["config_structs"][0] == {
        "config_keys_total": 1,
        "fields_total": 1,
        "name": "Config",
        "required_fields_total": 1,
        "source_file_path": "internal/service/service.go",
    }
    assert "keys" not in document["configuration"]["config_files"][0]
    assert document["configuration"]["config_files"][0]["keys_total"] == 2

    integrations = {(item["category"], item["name"]) for item in document["external_integrations"]}
    assert ("database", "net/http") not in integrations
    assert ("database", "DATABASE_URL") in integrations
    assert ("database", "sql") in integrations
    assert ("network", "chi") in integrations

    assert document["http_surface"]["confidence"] == "high"
    assert document["http_surface"]["detected"] is True
    assert document["http_surface"]["frameworks"] == ["chi", "net_http"]
    assert document["http_surface"]["unsupported_patterns"] == []
    assert len(document["http_surface"]["routes"]) == 1
    route = document["http_surface"]["routes"][0]
    assert {
        "file_path": route["file_path"],
        "framework": route["framework"],
        "line": route["line"],
        "method": route["method"],
        "path": route["path"],
    } == {
        "file_path": "cmd/api/main.go",
        "framework": "chi",
        "line": 13,
        "method": "GET",
        "path": "/health",
    }
    assert route["package"]["package_id"] == "github.com/acme/project/cmd/api#main"
    assert route["handler"]["expression"] == "service.Health"
    assert route["handler"]["symbol"]["qualified_name"] == "service.Health"
    assert document["budget"]["estimated_document_bytes"] == len(artifact_one.payload)
    assert document["budget"]["estimated_document_tokens"] > 0
    assert {item["source"] for item in document["budget"]["omitted_sections"]} == {
        "config_inventory.config_files.keys",
        "file_inventory.files",
        "go_symbols.symbols",
        "package_graph.edges",
        "package_graph.packages",
    }
    assert [item["artifact_kind"] for item in document["source_artifacts"]] == [
        "file_inventory",
        "go_symbols",
        "package_graph",
        "config_inventory",
    ]


def test_build_project_model_artifact_extracts_grouped_multiline_http_routes(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
require (
    github.com/gin-gonic/gin v1.10.0
    github.com/go-chi/chi/v5 v5.0.0
    github.com/gorilla/mux v1.8.1
)
""",
    )
    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import (
    "github.com/acme/project/internal/service"
    "github.com/gin-gonic/gin"
    "github.com/go-chi/chi/v5"
    "github.com/gorilla/mux"
)

func main() {
    r := chi.NewRouter()
    r.Route("/api", func(r chi.Router) {
        r.Get(
            "/health",
            service.Health,
        )
        r.MethodFunc(
            "POST",
            "/items",
            service.Health,
        )
        dynamicPath := "/dynamic"
        r.Get(dynamicPath, service.Health)
    })

    g := gin.Default()
    v1 := g.Group("/v1")
    v1.POST(
        "/users",
        service.Health,
    )

    m := mux.NewRouter()
    m.HandleFunc("/legacy", service.Health).Methods("GET", "POST")
}
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

func Health() {}
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)
    metadata = _snapshot_metadata(tmp_path, repo)

    document = _build_project_model_document(tmp_path, metadata)

    assert document["summary"]["http_routes_total"] == 5
    assert document["http_surface"]["frameworks"] == ["chi", "gin", "gorilla_mux"]
    routes = {
        (route["framework"], route["method"], route["path"]): route
        for route in document["http_surface"]["routes"]
    }

    assert ("chi", "GET", "/api/health") in routes
    assert ("chi", "POST", "/api/items") in routes
    assert ("gin", "POST", "/v1/users") in routes
    assert ("gorilla_mux", "GET", "/legacy") in routes
    assert ("gorilla_mux", "POST", "/legacy") in routes
    assert routes[("chi", "GET", "/api/health")]["handler"]["symbol"]["qualified_name"] == "service.Health"
    assert routes[("gin", "POST", "/v1/users")]["package"]["package_id"] == "github.com/acme/project/cmd/api#main"

    assert document["http_surface"]["unsupported_patterns"] == [
        {
            "expression": "dynamicPath",
            "file_path": "cmd/api/main.go",
            "framework": "chi",
            "kind": "dynamic_route_path",
            "line": 23,
            "reason": "route path is not a string literal",
        }
    ]


def test_build_project_model_artifact_describes_multilanguage_monorepo_units(
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "backend" / "go.mod",
        """module github.com/acme/backend

go 1.22
require github.com/gin-gonic/gin v1.10.0
""",
    )
    _write_text(
        tmp_path / "backend" / "cmd" / "api" / "main.go",
        """package main

import "github.com/gin-gonic/gin"

func main() {
    router := gin.Default()
    router.GET("/health", func(ctx *gin.Context) {})
}
""",
    )
    _write_text(
        tmp_path / "frontend" / "package.json",
        """{
  "name": "@acme/web",
  "scripts": {
    "dev": "vite --host 0.0.0.0",
    "build": "vite build",
    "test": "vitest"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "react": "^19.0.0",
    "vite": "^6.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
""",
    )
    _write_text(tmp_path / "frontend" / "src" / "pages" / "index.tsx", "export default function Home() { return null }\n")
    _write_text(tmp_path / "frontend" / "src" / "components" / "PostCard.tsx", "export function PostCard() { return null }\n")
    _write_text(tmp_path / "frontend" / "src" / "api" / "client.ts", "export const api = {}\n")
    _write_text(
        tmp_path / "docker-compose.yml",
        """services:
  api:
    build: ./backend
""",
    )
    _write_text(tmp_path / "docs" / "README.md", "# Docs\n")

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)
    metadata = _snapshot_metadata(tmp_path, repo)

    document = _build_project_model_document(tmp_path, metadata)
    units = {item["workspace_unit_id"]: item for item in document["workspace_units"]}

    assert set(units) == {"backend:backend", "docs:docs", "frontend:frontend", "infra:root"}
    backend = units["backend:backend"]
    assert backend["root_path"] == "backend"
    assert backend["languages"] == ["go"]
    assert backend["go"]["packages_total"] == 1
    assert backend["http_surface"] == {
        "detected": True,
        "frameworks": ["gin"],
        "routes_total": 1,
    }

    frontend = units["frontend:frontend"]
    assert frontend["name"] == "@acme/web"
    assert frontend["languages"] == ["configuration", "typescript"]
    assert frontend["frameworks"] == ["react", "vite"]
    assert frontend["javascript"]["package_manager"] is None
    assert frontend["javascript"]["route_directories"] == ["frontend/src/pages"]
    assert frontend["javascript"]["component_directories"] == ["frontend/src/components"]
    assert frontend["javascript"]["api_client_directories"] == ["frontend/src/api"]
    assert [item["name"] for item in frontend["javascript"]["scripts"]] == ["dev", "build", "test"]

    assert units["infra:root"]["file_counts"]["by_owner"] == {"infra": 1}
    assert units["docs:docs"]["file_counts"]["by_owner"] == {"docs": 1}
    assert document["go"]["important_packages"][0]["workspace_unit_id"] == "backend:backend"
    assert document["summary"]["workspace_units_total"] == 4


def _commit_all(repo: Repo, repo_root: Path) -> None:
    paths = [
        str(path.relative_to(repo_root))
        for path in sorted(repo_root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    ]
    repo.index.add(paths)
    actor = Actor("DopDoc", "dopdoc@example.com")
    repo.index.commit("init", author=actor, committer=actor)


def _snapshot_metadata(repo_root: Path, repo: Repo) -> dict[str, object]:
    commit = repo.head.commit
    metadata: dict[str, object] = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
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
    metadata["files_total"] = len(
        [path for path in repo_root.rglob("*") if path.is_file() and ".git" not in path.parts]
    )
    return metadata


def _build_project_model_document(repo_root: Path, metadata: dict[str, object]) -> dict[str, object]:
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
    package_graph = build_package_graph_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        go_symbols_artifact=go_symbols,
    )
    config_inventory = build_config_inventory_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
    )
    artifact = build_project_model_artifact(
        repo_root,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        file_inventory_artifact=file_inventory,
        go_symbols_artifact=go_symbols,
        package_graph_artifact=package_graph,
        config_inventory_artifact=config_inventory,
    )
    return json.loads(artifact.payload.decode("utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
