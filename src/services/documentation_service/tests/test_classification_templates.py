from app.pipeline.classification import classify_repository
from app.pipeline.templates import (
    get_section_templates,
    select_documentation_template,
)


def test_cobra_like_repository_selects_go_library_handbook() -> None:
    classification = classify_repository(
        {
            "project_model": {
                "summary": {
                    "packages_total": 12,
                    "entrypoint_packages_total": 0,
                    "http_routes_total": 0,
                    "has_tests": True,
                },
                "workspace_units": [
                    {
                        "name": "github.com/spf13/cobra",
                        "root_path": ".",
                        "unit_kind": "go_module",
                        "languages": ["go"],
                        "frameworks": ["go"],
                        "roles": ["library"],
                    }
                ],
                "code_outline": {
                    "important_symbols": [
                        {"name": "Command", "signature": "type Command struct"},
                        {"name": "Execute", "signature": "func (c *Command) Execute() error"},
                    ],
                },
            },
            "package_graph": {
                "summary": {
                    "packages_total": 12,
                    "modules_total": 1,
                    "entrypoint_packages_total": 0,
                },
                "modules": [{"module_path": "github.com/spf13/cobra"}],
                "packages": [{"name": "cobra", "package_id": "github.com/spf13/cobra#cobra"}],
            },
            "config_inventory": {"summary": {"api_specs_total": 0}},
        }
    )

    selection = select_documentation_template("developer_handbook", classification)
    section_keys = [section.key for section in get_section_templates(selection.effective_template_kind)]

    assert classification.repository_kind == "library"
    assert selection.effective_template_kind == "go_library_handbook"
    assert {"public_api", "command_lifecycle", "flags_and_args", "completions"}.issubset(
        section_keys
    )
    assert "change_report" in section_keys
    command_lifecycle = next(
        section for section in get_section_templates(selection.effective_template_kind)
        if section.key == "command_lifecycle"
    )
    assert "execute/run lifecycle" in command_lifecycle.must_cover
    assert "assuming Cobra unless evidence shows Cobra-specific names" in command_lifecycle.avoid


def test_cobra_like_backend_role_without_service_surface_still_selects_go_library() -> None:
    classification = classify_repository(
        {
            "project_model": {
                "summary": {
                    "packages_total": 18,
                    "entrypoint_packages_total": 0,
                    "http_routes_total": 0,
                    "has_tests": True,
                },
                "workspace_units": [
                    {
                        "name": "cobra",
                        "workspace_unit_id": "backend:.",
                        "root_path": ".",
                        "unit_kind": "backend",
                        "languages": ["go"],
                        "frameworks": ["go"],
                        "roles": ["backend"],
                    }
                ],
                "files": [{"path": "doc.go"}, {"path": "command.go"}, {"path": "flag_groups.go"}],
                "code_outline": {
                    "important_symbols": [
                        {"name": "Command", "signature": "type Command struct"},
                        {"name": "Execute", "signature": "func (c *Command) Execute() error"},
                        {"name": "AddCommand", "signature": "func (c *Command) AddCommand(cmds ...*Command)"},
                    ],
                },
            },
            "package_graph": {
                "summary": {
                    "packages_total": 18,
                    "modules_total": 1,
                    "entrypoint_packages_total": 0,
                },
                "modules": [{"module_path": "github.com/spf13/cobra", "dir_path": "."}],
                "packages": [
                    {
                        "name": "cobra",
                        "package_id": "github.com/spf13/cobra#cobra",
                        "dir_path": ".",
                    }
                ],
            },
            "config_inventory": {"summary": {"api_specs_total": 0}},
        }
    )

    selection = select_documentation_template("developer_handbook", classification)

    assert classification.repository_kind == "library"
    assert classification.signals["has_go_library_shape"] is True
    assert classification.scores["library"] > classification.scores["backend_service"]
    assert selection.effective_template_kind == "go_library_handbook"


def test_image_board_like_repository_selects_monorepo_web_app_handbook() -> None:
    classification = classify_repository(
        {
            "project_model": {
                "summary": {
                    "workspace_units_total": 4,
                    "http_routes_total": 12,
                    "has_tests": False,
                },
                "workspace_units": [
                    {
                        "name": "frontend",
                        "root_path": "frontend",
                        "unit_kind": "frontend",
                        "languages": ["typescript"],
                        "frameworks": ["react", "vite"],
                        "roles": ["frontend"],
                        "manifest_paths": ["frontend/package.json"],
                    },
                    {
                        "name": "boards-service",
                        "root_path": "backend/boards-service",
                        "unit_kind": "backend",
                        "languages": ["go"],
                        "frameworks": ["go", "gin"],
                        "roles": ["backend"],
                    },
                    {
                        "name": "infra",
                        "root_path": ".",
                        "unit_kind": "infra",
                        "frameworks": ["docker"],
                        "roles": ["infra"],
                    },
                ],
                "http_surface": {"detected": True, "routes_total": 12},
            },
            "package_graph": {
                "summary": {
                    "packages_total": 30,
                    "modules_total": 6,
                    "entrypoint_packages_total": 6,
                },
                "modules": [{"module_path": "gitlab.com/example/boards-service"}],
            },
            "config_inventory": {"summary": {"api_specs_total": 4}},
        }
    )

    selection = select_documentation_template("developer_handbook", classification)
    section_keys = [section.key for section in get_section_templates(selection.effective_template_kind)]

    assert classification.repository_kind == "monorepo_web_app"
    assert selection.effective_template_kind == "monorepo_web_app_handbook"
    assert {"service_map", "local_development", "request_flows", "api_surface", "frontend"}.issubset(
        section_keys
    )
    assert "change_report" in section_keys
    service_map = next(
        section for section in get_section_templates(selection.effective_template_kind)
        if section.key == "service_map"
    )
    assert "frontend units" in service_map.must_cover
    assert "architecture_map" in service_map.document_keys


def test_explicit_typed_template_bypasses_classified_selection() -> None:
    classification = classify_repository({"project_model": {}, "package_graph": {}, "config_inventory": {}})

    selection = select_documentation_template("go_library_handbook", classification)

    assert selection.selection_mode == "explicit"
    assert selection.effective_template_kind == "go_library_handbook"
