import configparser
import hashlib
import json
import re
import tomllib
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key
from app.artifacts.source_scope import (
    SOURCE_SCOPE_GENERATED,
    SOURCE_SCOPE_INFRA,
    SOURCE_SCOPE_RUNTIME,
    SOURCE_SCOPE_VENDOR,
    runtime_scope_from_source_scope,
    source_scope_from_record,
)

CONFIG_INVENTORY_ARTIFACT_KIND = "config_inventory"
CONFIG_INVENTORY_SCHEMA_VERSION = 1

_ENV_CALL_RE = re.compile(r"\b(?:os|syscall)\.(Getenv|LookupEnv)\s*\(")
_GO_FUNC_START_RE = re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\((?P<params>[^)]*)\)")
_BARE_CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\(")
_FLAG_CALL_RE = re.compile(
    r"\b(?:flag|pflag)\."
    r"(String|Bool|Int|Int64|Uint|Uint64|Float64|Duration|"
    r"StringVar|BoolVar|IntVar|Int64Var|UintVar|Uint64Var|Float64Var|DurationVar|Var)\s*\("
)
_STRUCT_START_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+struct\s*\{")
_STRUCT_TAG_RE = re.compile(r'([A-Za-z_]\w*):"([^"]*)"')
_CONFIG_TAGS = {"json", "yaml", "toml", "mapstructure", "env", "envconfig"}
_RUNTIME_CONFIG_TAGS = {"env", "envconfig", "mapstructure"}
_DATA_CONTRACT_TAGS = {"json", "binding", "form", "uri", "header", "param", "query", "swagger", "example"}
_PERSISTENCE_TAGS = {"gorm", "db", "bson", "sql"}
_STRUCT_MODEL_TAGS = _CONFIG_TAGS | _DATA_CONTRACT_TAGS | _PERSISTENCE_TAGS | {"default", "required", "validate"}
_CONFIG_NAME_PARTS = {"config", "configuration", "settings", "options", "option", "env", "environment"}
_AUTH_CLAIM_NAME_PARTS = {"claims", "claim", "jwtclaims", "tokenclaims"}
_REDACT_KEY_PARTS = {"secret", "password", "passwd", "token", "apikey", "api_key", "private_key"}
_MAX_CONFIG_FILE_BYTES = 256 * 1024
_MAX_CONFIG_KEYS_PER_FILE = 256
_MAX_CONFIG_NESTING_DEPTH = 8
_LOCKFILE_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "pnpm-lock.yml",
    "bun.lockb",
    "bun.lock",
    "go.sum",
    "cargo.lock",
    "poetry.lock",
    "pipfile.lock",
}
_API_SPEC_FILENAMES = {
    "api-docs.json",
    "api-docs.yaml",
    "api-docs.yml",
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
}
_API_SPEC_PATH_PARTS = {"api-docs", "apidocs", "openapi", "swagger"}
_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def build_config_inventory_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    file_inventory_artifact: BuiltAnalysisArtifact | dict[str, Any],
    go_symbols_artifact: BuiltAnalysisArtifact | dict[str, Any],
) -> BuiltAnalysisArtifact:
    repo_root = Path(repo_path)
    file_inventory = _load_artifact_document(file_inventory_artifact)
    go_symbols = _load_artifact_document(go_symbols_artifact)
    source_index = _build_go_source_index(go_symbols)

    env_vars, dynamic_env_references, flags, dynamic_flag_references, config_structs, data_contracts = _scan_go_sources(
        repo_root,
        go_symbols,
        source_index,
    )
    config_files, api_specs, dependency_locks = _scan_config_files(repo_root, file_inventory)

    env_vars.sort(key=lambda item: (item["key"], item["source"]["file_path"], item["source"]["start_line"]))
    dynamic_env_references.sort(key=lambda item: (item["source"]["file_path"], item["source"]["start_line"], item["expression"]))
    flags.sort(key=lambda item: (item["name"], item["source"]["file_path"], item["source"]["start_line"]))
    dynamic_flag_references.sort(key=lambda item: (item["source"]["file_path"], item["source"]["start_line"], item["expression"]))
    config_structs.sort(key=lambda item: (item["source"]["file_path"], item["source"]["start_line"], item["name"]))
    data_contracts.sort(key=lambda item: (item["source"]["file_path"], item["source"]["start_line"], item["name"]))
    config_files.sort(key=lambda item: item["path"])
    api_specs.sort(key=lambda item: item["path"])
    dependency_locks.sort(key=lambda item: item["path"])

    config_file_keys_total = sum(len(item["keys"]) for item in config_files)
    config_files_truncated_total = sum(1 for item in config_files if item["truncated"])
    runtime_env_vars = [item for item in env_vars if item["source_scope"] == SOURCE_SCOPE_RUNTIME]
    runtime_flags = [item for item in flags if item["source_scope"] == SOURCE_SCOPE_RUNTIME]
    runtime_config_structs = [
        item for item in config_structs if item["source_scope"] == SOURCE_SCOPE_RUNTIME
    ]
    primary_config_files = [
        item for item in config_files if item["source_scope"] in {SOURCE_SCOPE_RUNTIME, SOURCE_SCOPE_INFRA}
    ]
    runtime_config_file_keys_total = sum(len(item["keys"]) for item in primary_config_files)
    required_items_total = (
        sum(1 for item in env_vars if item["required"])
        + sum(1 for item in flags if item["required"])
        + sum(
            1
            for config_struct in config_structs
            for field in config_struct["fields"]
            if field["required"]
        )
    )
    runtime_required_items_total = (
        sum(1 for item in runtime_env_vars if item["required"])
        + sum(1 for item in runtime_flags if item["required"])
        + sum(
            1
            for config_struct in runtime_config_structs
            for field in config_struct["fields"]
            if field["required"]
        )
    )
    summary = {
        "env_vars_total": len(env_vars),
        "runtime_env_vars_total": len(runtime_env_vars),
        "dynamic_env_references_total": len(dynamic_env_references),
        "flags_total": len(flags),
        "runtime_flags_total": len(runtime_flags),
        "dynamic_flag_references_total": len(dynamic_flag_references),
        "config_structs_total": len(config_structs),
        "runtime_config_structs_total": len(runtime_config_structs),
        "data_contracts_total": len(data_contracts),
        "data_contract_kind_counts": dict(sorted(Counter(item["model_kind"] for item in data_contracts).items())),
        "config_files_total": len(config_files),
        "config_file_keys_total": config_file_keys_total,
        "runtime_config_file_keys_total": runtime_config_file_keys_total,
        "config_files_truncated_total": config_files_truncated_total,
        "api_specs_total": len(api_specs),
        "api_spec_kind_counts": dict(sorted(Counter(item["spec_kind"] for item in api_specs).items())),
        "dependency_locks_total": len(dependency_locks),
        "dependency_lock_kind_counts": dict(sorted(Counter(item["lockfile_kind"] for item in dependency_locks).items())),
        "configuration_items_total": len(env_vars) + len(flags) + len(config_structs) + config_file_keys_total,
        "runtime_configuration_items_total": (
            len(runtime_env_vars)
            + len(runtime_flags)
            + len(runtime_config_structs)
            + runtime_config_file_keys_total
        ),
        "required_items_total": required_items_total,
        "runtime_required_items_total": runtime_required_items_total,
        "config_file_format_counts": dict(sorted(Counter(item["format"] for item in config_files).items())),
        "source_scope_counts": {
            "env_vars": dict(sorted(Counter(item["source_scope"] for item in env_vars).items())),
            "flags": dict(sorted(Counter(item["source_scope"] for item in flags).items())),
            "dynamic_env_references": dict(sorted(Counter(item["source_scope"] for item in dynamic_env_references).items())),
            "dynamic_flag_references": dict(sorted(Counter(item["source_scope"] for item in dynamic_flag_references).items())),
            "config_structs": dict(sorted(Counter(item["source_scope"] for item in config_structs).items())),
            "data_contracts": dict(sorted(Counter(item["source_scope"] for item in data_contracts).items())),
            "config_files": dict(sorted(Counter(item["source_scope"] for item in config_files).items())),
            "api_specs": dict(sorted(Counter(item["source_scope"] for item in api_specs).items())),
            "dependency_locks": dict(sorted(Counter(item["source_scope"] for item in dependency_locks).items())),
        },
        "config_file_parse_limits": {
            "max_file_bytes": _MAX_CONFIG_FILE_BYTES,
            "max_keys_per_file": _MAX_CONFIG_KEYS_PER_FILE,
            "max_nesting_depth": _MAX_CONFIG_NESTING_DEPTH,
        },
    }

    document = {
        "artifact_kind": CONFIG_INVENTORY_ARTIFACT_KIND,
        "schema_version": CONFIG_INVENTORY_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": summary,
        "env_vars": env_vars,
        "dynamic_env_references": dynamic_env_references,
        "flags": flags,
        "dynamic_flag_references": dynamic_flag_references,
        "config_structs": config_structs,
        "data_contracts": data_contracts,
        "config_files": config_files,
        "api_specs": api_specs,
        "dependency_locks": dependency_locks,
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=CONFIG_INVENTORY_ARTIFACT_KIND,
        schema_version=CONFIG_INVENTORY_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=analysis_artifact_storage_key(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            artifact_kind=CONFIG_INVENTORY_ARTIFACT_KIND,
            schema_version=CONFIG_INVENTORY_SCHEMA_VERSION,
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=summary["configuration_items_total"],
        payload=payload,
        summary=summary,
    )


def _load_artifact_document(artifact: BuiltAnalysisArtifact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, BuiltAnalysisArtifact):
        return json.loads(artifact.payload.decode("utf-8"))

    return artifact


def _build_go_source_index(go_symbols: dict[str, Any]) -> dict[str, Any]:
    packages_by_file = {item["path"]: item.get("package") for item in go_symbols.get("files", [])}
    source_scopes_by_file = {
        item["path"]: source_scope_from_record(item)
        for item in go_symbols.get("files", [])
    }
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    for symbol in go_symbols.get("symbols", []):
        symbols_by_file.setdefault(symbol["file_path"], []).append(symbol)

    for symbols in symbols_by_file.values():
        symbols.sort(key=lambda item: (item["start_line"], item["end_line"], item["qualified_name"]))

    return {
        "packages_by_file": packages_by_file,
        "source_scopes_by_file": source_scopes_by_file,
        "symbols_by_file": symbols_by_file,
    }


def _scan_go_sources(
    repo_root: Path,
    go_symbols: dict[str, Any],
    source_index: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    env_vars: list[dict[str, Any]] = []
    dynamic_env_references: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    dynamic_flag_references: list[dict[str, Any]] = []
    config_structs: list[dict[str, Any]] = []
    data_contracts: list[dict[str, Any]] = []
    source_files: list[tuple[str, list[str]]] = []

    for file_record in go_symbols.get("files", []):
        source_scope = source_scope_from_record(file_record)
        if source_scope in {SOURCE_SCOPE_VENDOR, SOURCE_SCOPE_GENERATED}:
            continue

        path = file_record["path"]
        source_path = repo_root / path
        text = source_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        source_files.append((path, lines))

    env_wrappers = _detect_env_key_wrappers(source_files)

    for path, lines in source_files:
        file_env_vars, file_dynamic_env_references = _extract_env_vars(path, lines, source_index, env_wrappers)
        file_flags, file_dynamic_flag_references = _extract_flags(path, lines, source_index)
        file_config_structs, file_data_contracts = _extract_struct_models(path, lines, source_index)
        env_vars.extend(file_env_vars)
        dynamic_env_references.extend(file_dynamic_env_references)
        flags.extend(file_flags)
        dynamic_flag_references.extend(file_dynamic_flag_references)
        config_structs.extend(file_config_structs)
        data_contracts.extend(file_data_contracts)

    return env_vars, dynamic_env_references, flags, dynamic_flag_references, config_structs, data_contracts


def _extract_env_vars(
    path: str,
    lines: list[str],
    source_index: dict[str, Any],
    env_wrappers: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    dynamic_references: list[dict[str, Any]] = []

    for line_index, line in enumerate(lines):
        for match in _ENV_CALL_RE.finditer(line):
            args = _parse_call_args(line, match.end() - 1)
            if not args:
                continue

            key = _parse_go_literal(args[0])
            if not isinstance(key, str) or not key:
                source = _source_ref(path, line_index + 1, source_index)
                if _is_wrapper_definition_env_reference(path, line_index + 1, args[0], env_wrappers):
                    continue

                dynamic_references.append(
                    _dynamic_reference(
                        source,
                        kind="dynamic_env_reference",
                        accessor=f"os.{match.group(1)}",
                        expression=args[0],
                        reason="env key is not a string literal",
                    )
                )
                continue

            required, required_reason = _required_env_hint(lines, line_index, match.group(1), key)
            source = _source_ref(path, line_index + 1, source_index)
            findings.append(
                _with_finding_scope(
                    {
                        "key": key,
                        "accessor": f"os.{match.group(1)}",
                        "default_value": None,
                        "required": required,
                        "required_reason": required_reason,
                        "confidence": "high",
                        "source_expression": _compact_expression(line),
                        "source": source,
                    },
                    source,
                )
            )

        if line.lstrip().startswith("func "):
            continue

        for match in _BARE_CALL_RE.finditer(line):
            wrapper = env_wrappers.get(match.group("name"))
            if wrapper is None:
                continue

            args = _parse_call_args(line, match.end() - 1)
            key_index = wrapper["key_arg_index"]
            if len(args) <= key_index:
                continue

            source = _source_ref(path, line_index + 1, source_index)
            key = _parse_go_literal(args[key_index])
            if not isinstance(key, str) or not key:
                dynamic_references.append(
                    _dynamic_reference(
                        source,
                        kind="dynamic_env_reference",
                        accessor=wrapper["name"],
                        expression=args[key_index],
                        reason="env wrapper key argument is not a string literal",
                    )
                )
                continue

            default_value = None
            default_arg_index = wrapper.get("default_arg_index")
            if isinstance(default_arg_index, int) and len(args) > default_arg_index:
                default_value = _parse_go_literal(args[default_arg_index])

            findings.append(
                _with_finding_scope(
                    {
                        "key": key,
                        "accessor": wrapper["name"],
                        "default_value": default_value,
                        "required": False,
                        "required_reason": None,
                        "confidence": "medium",
                        "source_expression": _compact_expression(line),
                        "source": source,
                    },
                    source,
                )
            )

    return findings, dynamic_references


def _extract_flags(path: str, lines: list[str], source_index: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    dynamic_references: list[dict[str, Any]] = []

    for line_index, line in enumerate(lines):
        for match in _FLAG_CALL_RE.finditer(line):
            flag_type = match.group(1)
            args = _parse_call_args(line, match.end() - 1)
            parsed, dynamic_expression = _parse_flag_call(flag_type, args)
            source = _source_ref(path, line_index + 1, source_index)
            if dynamic_expression is not None:
                dynamic_references.append(
                    _dynamic_reference(
                        source,
                        kind="dynamic_flag_reference",
                        accessor=f"flag.{flag_type}",
                        expression=dynamic_expression,
                        reason="flag name is not a string literal",
                    )
                )
                continue

            if parsed is None:
                continue

            parsed["source"] = source
            parsed["confidence"] = "high"
            parsed["source_expression"] = _compact_expression(line)
            parsed = _with_finding_scope(parsed, source)
            findings.append(parsed)

    return findings, dynamic_references


def _parse_flag_call(flag_type: str, args: list[str]) -> tuple[dict[str, Any] | None, str | None]:
    is_var = flag_type.endswith("Var")
    is_custom_var = flag_type == "Var"
    if (is_var and len(args) < 4) or (is_custom_var and len(args) < 3) or (not is_var and len(args) < 3):
        return None, None

    if is_custom_var:
        name_arg = args[1]
        default_arg = None
        usage_arg = args[2]
        destination = args[0].strip()
    elif is_var:
        name_arg = args[1]
        default_arg = args[2]
        usage_arg = args[3]
        destination = args[0].strip()
    else:
        name_arg = args[0]
        default_arg = args[1]
        usage_arg = args[2]
        destination = None

    name = _parse_go_literal(name_arg)
    if not isinstance(name, str) or not name:
        return None, name_arg

    usage = _parse_go_literal(usage_arg)
    default_value = _parse_go_literal(default_arg) if default_arg is not None else None
    required = isinstance(usage, str) and "required" in usage.lower()

    return (
        {
            "name": name,
            "flag_type": flag_type.removesuffix("Var").lower(),
            "default_value": default_value,
            "default_value_raw": default_arg.strip() if default_arg is not None else None,
            "usage": usage if isinstance(usage, str) else usage_arg.strip(),
            "required": required,
            "required_reason": "usage_mentions_required" if required else None,
            "destination": destination,
        },
        None,
    )


def _detect_env_key_wrappers(source_files: list[tuple[str, list[str]]]) -> dict[str, dict[str, Any]]:
    wrappers: dict[str, dict[str, Any]] = {}

    for path, lines in source_files:
        index = 0
        while index < len(lines):
            match = _GO_FUNC_START_RE.match(lines[index])
            if match is None:
                index += 1
                continue

            block_lines, end_index = _collect_block(lines, index)
            params = _parse_go_params(match.group("params"))
            body = "\n".join(block_lines)
            for param_index, param_name in enumerate(params):
                if re.search(rf"\b(?:os|syscall)\.(?:Getenv|LookupEnv)\s*\(\s*{re.escape(param_name)}\s*\)", body):
                    wrapper = wrappers.setdefault(
                        match.group("name"),
                        {
                            "name": match.group("name"),
                            "key_arg_index": param_index,
                            "default_arg_index": param_index + 1 if len(params) > param_index + 1 else None,
                            "definitions": [],
                        },
                    )
                    wrapper["definitions"].append(
                        {
                            "path": path,
                            "start_line": index + 1,
                            "end_line": end_index + 1,
                            "key_param": param_name,
                        }
                    )
                    break

            index = end_index + 1

    return wrappers


def _parse_go_params(params_text: str) -> list[str]:
    params: list[str] = []
    pending_names: list[str] = []
    for part in _split_top_level(params_text):
        tokens = part.strip().split()
        if len(tokens) == 1:
            name = tokens[0].strip().strip("*").strip()
            if name and re.match(r"^[A-Za-z_]\w*$", name):
                pending_names.append(name)
            continue

        if len(tokens) < 2:
            continue

        for name in pending_names + tokens[:-1]:
            normalized = name.strip().strip("*").strip()
            if normalized and re.match(r"^[A-Za-z_]\w*$", normalized):
                params.append(normalized)
        pending_names = []

    return params


def _is_wrapper_definition_env_reference(
    path: str,
    line: int,
    expression: str,
    env_wrappers: dict[str, dict[str, Any]],
) -> bool:
    compact = _compact_expression(expression)
    for wrapper in env_wrappers.values():
        for definition in wrapper.get("definitions", []):
            if (
                definition.get("path") == path
                and definition.get("start_line", 0) <= line <= definition.get("end_line", 0)
                and compact == definition.get("key_param")
            ):
                return True

    return False


def _extract_struct_models(
    path: str,
    lines: list[str],
    source_index: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config_structs: list[dict[str, Any]] = []
    data_contracts: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        match = _STRUCT_START_RE.match(lines[index])
        if match is None:
            index += 1
            continue

        name = match.group(1)
        start_line = index + 1
        block_lines, end_index = _collect_struct_block(lines, index)
        fields = _extract_struct_fields(block_lines, start_line)
        if fields:
            source = _source_ref(path, start_line, source_index, end_line=end_index + 1)
            model_kind = _classify_struct_model(name, path, fields)
            model = _with_finding_scope(
                {
                    "name": name,
                    "model_kind": model_kind,
                    "fields": fields,
                    "source": source,
                },
                source,
            )
            if model_kind == "runtime_config":
                config_structs.append(model)
            elif model_kind != "unknown":
                data_contracts.append(
                    {
                        **model,
                        "fields": _contract_fields(fields),
                    }
                )

        index = end_index + 1

    return config_structs, data_contracts


def _collect_block(lines: list[str], start_index: int) -> tuple[list[str], int]:
    block_lines: list[str] = []
    depth = 0
    end_index = start_index
    seen_open = False
    for index in range(start_index, len(lines)):
        line = lines[index]
        block_lines.append(line)
        depth += line.count("{") - line.count("}")
        seen_open = seen_open or "{" in line
        if seen_open and index > start_index and depth <= 0:
            end_index = index
            break

    return block_lines, end_index


def _collect_struct_block(lines: list[str], start_index: int) -> tuple[list[str], int]:
    block_lines: list[str] = []
    depth = 0
    end_index = start_index
    for index in range(start_index, len(lines)):
        line = lines[index]
        block_lines.append(line)
        depth += line.count("{") - line.count("}")
        if index > start_index and depth <= 0:
            end_index = index
            break

    return block_lines, end_index


def _extract_struct_fields(block_lines: list[str], start_line: int) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []

    for offset, line in enumerate(block_lines[1:], start=1):
        if "}" in line:
            break

        tag_match = re.search(r"`([^`]*)`", line)
        if tag_match is None:
            continue

        tag_map = dict(_STRUCT_TAG_RE.findall(tag_match.group(1)))
        config_keys = _config_keys_from_tags(tag_map)
        if not config_keys and not any(key in tag_map for key in _STRUCT_MODEL_TAGS):
            continue

        field_match = re.match(r"^\s*([A-Za-z_]\w*)\s+(.+?)(?:\s+`|$)", line)
        if field_match is None:
            continue

        required = _tag_is_required(tag_map)
        fields.append(
            {
                "name": field_match.group(1),
                "type": field_match.group(2).strip(),
                "config_keys": config_keys,
                "tags": tag_map,
                "default_value": tag_map.get("default"),
                "required": required,
                "required_reason": "struct_tag" if required else None,
                "line": start_line + offset,
            }
        )

    fields.sort(key=lambda item: (item["line"], item["name"]))
    return fields


def _classify_struct_model(name: str, path: str, fields: list[dict[str, Any]]) -> str:
    tag_names = {
        tag_name
        for field in fields
        for tag_name in field.get("tags", {})
    }
    normalized_name = name.lower()
    path_parts = {part.lower() for part in PurePosixPath(path).parts}
    config_context = _looks_like_config_name(normalized_name) or bool(path_parts.intersection(_CONFIG_NAME_PARTS))

    if tag_names.intersection(_RUNTIME_CONFIG_TAGS):
        return "runtime_config"
    if config_context and (tag_names.intersection({"json", "yaml", "toml"}) or tag_names.intersection({"default", "required"})):
        return "runtime_config"
    if tag_names.intersection(_PERSISTENCE_TAGS):
        return "persistence_model"
    if any(part in normalized_name for part in _AUTH_CLAIM_NAME_PARTS):
        return "auth_claims"
    if tag_names.intersection(_DATA_CONTRACT_TAGS):
        return "api_contract"

    return "unknown"


def _contract_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contracts = []
    for field in fields:
        tags = field.get("tags", {})
        contract_keys = [
            {"source": tag_name, "key": value.split(",", 1)[0].strip()}
            for tag_name, value in sorted(tags.items())
            if tag_name in _DATA_CONTRACT_TAGS | _PERSISTENCE_TAGS and value and value.split(",", 1)[0].strip() != "-"
        ]
        contracts.append(
            {
                "name": field["name"],
                "type": field["type"],
                "contract_keys": contract_keys,
                "tags": tags,
                "required": field.get("required", False),
                "line": field["line"],
            }
        )

    return contracts


def _looks_like_config_name(name: str) -> bool:
    return any(part in name for part in _CONFIG_NAME_PARTS)


def _config_keys_from_tags(tag_map: dict[str, str]) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    for tag_name in sorted(_CONFIG_TAGS):
        value = tag_map.get(tag_name)
        if not value:
            continue

        normalized = value.split(",", 1)[0].strip()
        if not normalized or normalized == "-":
            continue

        keys.append({"source": tag_name, "key": normalized})

    return keys


def _scan_config_files(
    repo_root: Path,
    file_inventory: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    config_files: list[dict[str, Any]] = []
    api_specs: list[dict[str, Any]] = []
    dependency_locks: list[dict[str, Any]] = []

    for file_record in file_inventory.get("files", []):
        if file_record.get("is_binary"):
            continue

        path = file_record["path"]
        source_scope = source_scope_from_record(file_record)
        runtime_scope = runtime_scope_from_source_scope(source_scope)
        if _is_vendor_path(path):
            continue

        if file_record.get("kind") == "dependency_lock" or _is_lockfile_path(path):
            text, file_truncated = _read_text_with_cap(repo_root / path, _MAX_CONFIG_FILE_BYTES)
            dependency_locks.append(
                _summarize_dependency_lock(
                    path,
                    text,
                    file_record,
                    truncated=file_truncated,
                    source_scope=source_scope,
                )
            )
            continue

        config_format = _config_format(path)
        if file_record.get("kind") == "api_spec" or file_record.get("is_api_spec"):
            if config_format is None:
                continue

            text, file_truncated = _read_text_with_cap(repo_root / path, _MAX_CONFIG_FILE_BYTES)
            api_specs.append(
                _summarize_api_spec(
                    path,
                    config_format,
                    text,
                    file_record,
                    source="file_classification",
                    truncated=file_truncated,
                    source_scope=source_scope,
                    runtime_scope=runtime_scope,
                )
            )
            continue

        if file_record.get("kind") != "config":
            continue

        if config_format is None:
            continue

        source_path = repo_root / path
        text, file_truncated = _read_text_with_cap(source_path, _MAX_CONFIG_FILE_BYTES)
        if _looks_like_api_spec_document(path, text, config_format):
            api_specs.append(
                _summarize_api_spec(
                    path,
                    config_format,
                    text,
                    file_record,
                    source="content_hints",
                    truncated=file_truncated,
                    source_scope=source_scope,
                    runtime_scope=runtime_scope,
                )
            )
            continue

        keys, parse_error, keys_truncated, truncation_reason = _extract_config_file_keys(
            text,
            config_format,
            file_truncated=file_truncated,
        )
        config_files.append(
            {
                "path": path,
                "format": config_format,
                "keys": keys,
                "parse_error": parse_error,
                "truncated": file_truncated or keys_truncated,
                "truncation_reason": "max_file_bytes_exceeded" if file_truncated else truncation_reason,
                "size_bytes": file_record.get("size_bytes", 0),
                "line_count": file_record.get("line_count", 0),
                "source_scope": source_scope,
                "runtime_scope": runtime_scope,
            }
        )

    return config_files, api_specs, dependency_locks


def _extract_config_file_keys(
    text: str,
    config_format: str,
    *,
    file_truncated: bool = False,
) -> tuple[list[dict[str, Any]], bool, bool, str | None]:
    if file_truncated:
        return [], False, True, "max_file_bytes_exceeded"

    try:
        if config_format == "json":
            keys, truncated, reason = _flatten_config_mapping(json.loads(text))
            return keys, False, truncated, reason
        if config_format == "toml":
            keys, truncated, reason = _flatten_config_mapping(tomllib.loads(text))
            return keys, False, truncated, reason
        if config_format == "yaml":
            keys, truncated, reason = _limit_config_keys(_parse_yaml_like_keys(text))
            return keys, False, truncated, reason
        if config_format == "dotenv":
            keys, truncated, reason = _limit_config_keys(_parse_env_like_keys(text))
            return keys, False, truncated, reason
        if config_format == "properties":
            keys, truncated, reason = _limit_config_keys(_parse_properties_like_keys(text))
            return keys, False, truncated, reason
        if config_format == "ini":
            keys, truncated, reason = _limit_config_keys(_parse_ini_keys(text))
            return keys, False, truncated, reason
    except Exception:
        return [], True, False, None

    return [], False, False, None


def _flatten_config_mapping(
    value: Any,
    prefix: str = "",
    *,
    depth: int = 0,
    keys: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool, str | None]:
    if keys is None:
        keys = []

    if len(keys) >= _MAX_CONFIG_KEYS_PER_FILE:
        return keys, True, "max_keys_per_file_exceeded"

    if isinstance(value, dict):
        if depth >= _MAX_CONFIG_NESTING_DEPTH:
            if prefix:
                keys.append(
                    {
                        "key": prefix,
                        "value_kind": "object",
                        "value_preview": None,
                        "line": None,
                    }
                )
            return keys, True, "max_nesting_depth_exceeded"

        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            keys, truncated, reason = _flatten_config_mapping(
                value[key],
                child_prefix,
                depth=depth + 1,
                keys=keys,
            )
            if truncated:
                return keys, truncated, reason
        return keys, False, None

    keys.append(
        {
            "key": prefix,
            "value_kind": _value_kind(value),
            "value_preview": _safe_preview(prefix, value),
            "line": None,
        }
    )
    return keys, False, None


def _limit_config_keys(keys: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool, str | None]:
    keys.sort(key=lambda item: item["key"])
    if len(keys) <= _MAX_CONFIG_KEYS_PER_FILE:
        return keys, False, None

    return keys[:_MAX_CONFIG_KEYS_PER_FILE], True, "max_keys_per_file_exceeded"


def _read_text_with_cap(path: Path, max_bytes: int) -> tuple[str, bool]:
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)

    truncated = len(raw) > max_bytes
    return raw[:max_bytes].decode("utf-8", errors="replace"), truncated


def _looks_like_api_spec_document(path: str, text: str, config_format: str) -> bool:
    if config_format not in {"json", "yaml"}:
        return False

    if _is_api_spec_path(path):
        return True

    if config_format == "json":
        try:
            return _is_api_spec_mapping(json.loads(text))
        except Exception:
            return _has_api_spec_text_hints(text)

    return _has_api_spec_text_hints(text)


def _summarize_api_spec(
    path: str,
    config_format: str,
    text: str,
    file_record: dict[str, Any],
    *,
    source: str,
    truncated: bool,
    source_scope: str,
    runtime_scope: bool,
) -> dict[str, Any]:
    summary = {
        "path": path,
        "format": config_format,
        "spec_kind": "unknown",
        "spec_version": None,
        "title": None,
        "version": None,
        "paths_total": 0,
        "operations_total": 0,
        "source": source,
        "parse_error": False,
        "truncated": truncated,
        "truncation_reason": "max_file_bytes_exceeded" if truncated else None,
        "size_bytes": file_record.get("size_bytes", 0),
        "line_count": file_record.get("line_count", 0),
        "source_scope": source_scope,
        "runtime_scope": runtime_scope,
    }

    try:
        if config_format == "json" and not truncated:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                summary.update(_summarize_api_spec_mapping(parsed))
                return summary
    except Exception:
        summary["parse_error"] = True

    summary.update(_summarize_api_spec_text(text))
    return summary


def _summarize_dependency_lock(
    path: str,
    text: str,
    file_record: dict[str, Any],
    *,
    truncated: bool,
    source_scope: str,
) -> dict[str, Any]:
    lockfile_kind = _lockfile_kind(path)
    dependencies_total = _dependency_lock_dependencies_total(lockfile_kind, text) if not truncated else 0
    return {
        "path": path,
        "lockfile_kind": lockfile_kind,
        "package_manager": _lockfile_package_manager(lockfile_kind),
        "dependencies_total": dependencies_total,
        "parse_error": False,
        "truncated": truncated,
        "truncation_reason": "max_file_bytes_exceeded" if truncated else None,
        "size_bytes": file_record.get("size_bytes", 0),
        "line_count": file_record.get("line_count", 0),
        "source_scope": source_scope,
        "runtime_scope": False,
    }


def _dependency_lock_dependencies_total(lockfile_kind: str, text: str) -> int:
    if lockfile_kind in {"npm_package_lock", "npm_shrinkwrap"}:
        try:
            parsed = json.loads(text)
        except Exception:
            return 0

        if isinstance(parsed, dict) and isinstance(parsed.get("packages"), dict):
            return max(0, len(parsed["packages"]) - (1 if "" in parsed["packages"] else 0))
        if isinstance(parsed, dict) and isinstance(parsed.get("dependencies"), dict):
            return len(parsed["dependencies"])
        return 0

    if lockfile_kind == "go_sum":
        modules = {
            line.split()[0]
            for line in text.splitlines()
            if line.strip() and len(line.split()) >= 2
        }
        return len(modules)

    if lockfile_kind in {"yarn_lock", "pnpm_lock"}:
        return sum(1 for line in text.splitlines() if line and not line.startswith(" ") and ":" in line)

    return 0


def _lockfile_kind(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    if name == "package-lock.json":
        return "npm_package_lock"
    if name == "npm-shrinkwrap.json":
        return "npm_shrinkwrap"
    if name == "yarn.lock":
        return "yarn_lock"
    if name in {"pnpm-lock.yaml", "pnpm-lock.yml"}:
        return "pnpm_lock"
    if name in {"bun.lock", "bun.lockb"}:
        return "bun_lock"
    if name == "go.sum":
        return "go_sum"
    if name == "cargo.lock":
        return "cargo_lock"
    if name == "poetry.lock":
        return "poetry_lock"
    if name == "pipfile.lock":
        return "pipfile_lock"
    return "unknown"


def _lockfile_package_manager(lockfile_kind: str) -> str | None:
    return {
        "npm_package_lock": "npm",
        "npm_shrinkwrap": "npm",
        "yarn_lock": "yarn",
        "pnpm_lock": "pnpm",
        "bun_lock": "bun",
        "go_sum": "go",
        "cargo_lock": "cargo",
        "poetry_lock": "poetry",
        "pipfile_lock": "pipenv",
    }.get(lockfile_kind)


def _summarize_api_spec_mapping(value: dict[str, Any]) -> dict[str, Any]:
    spec_kind = "openapi" if "openapi" in value else "swagger" if "swagger" in value else "unknown"
    info = value.get("info") if isinstance(value.get("info"), dict) else {}
    paths = value.get("paths") if isinstance(value.get("paths"), dict) else {}
    operations_total = 0
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue

        operations_total += sum(1 for method in path_item if str(method).lower() in _HTTP_METHODS)

    return {
        "spec_kind": spec_kind,
        "spec_version": value.get("openapi") or value.get("swagger"),
        "title": info.get("title"),
        "version": info.get("version"),
        "paths_total": len(paths),
        "operations_total": operations_total,
    }


def _summarize_api_spec_text(text: str) -> dict[str, Any]:
    version_match = re.search(
        r'(?mi)(?:^|[{\n,]\s*)["\']?(openapi|swagger)["\']?\s*:\s*["\']?([^"\'\n,#}]+)',
        text,
    )
    title = _yaml_info_scalar(text, "title")
    app_version = _yaml_info_scalar(text, "version")
    paths_total, operations_total = _count_yaml_api_paths(text)

    spec_kind = version_match.group(1).lower() if version_match else "unknown"
    return {
        "spec_kind": spec_kind,
        "spec_version": version_match.group(2).strip() if version_match else None,
        "title": title,
        "version": app_version,
        "paths_total": paths_total,
        "operations_total": operations_total,
    }


def _yaml_info_scalar(text: str, key: str) -> str | None:
    info_indent: int | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if info_indent is None:
            if stripped == "info:":
                info_indent = indent
            continue

        if indent <= info_indent:
            return None

        match = re.match(rf"^{re.escape(key)}\s*:\s*['\"]?([^'\"\n#]+)", stripped)
        if match is not None:
            return match.group(1).strip()

    return None


def _count_yaml_api_paths(text: str) -> tuple[int, int]:
    paths_indent: int | None = None
    current_path_indent: int | None = None
    paths_total = 0
    operations_total = 0

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if paths_indent is None:
            if re.match(r"^paths\s*:\s*$", stripped):
                paths_indent = indent
            continue

        if indent <= paths_indent:
            break

        key_match = re.match(r"^['\"]?([^:'\"]+)['\"]?\s*:\s*(?:#.*)?$", stripped)
        if key_match is None:
            continue

        key = key_match.group(1)
        if key.startswith("/") and (current_path_indent is None or indent <= current_path_indent):
            current_path_indent = indent
            paths_total += 1
            continue

        if current_path_indent is not None and indent > current_path_indent and key.lower() in _HTTP_METHODS:
            operations_total += 1

    return paths_total, operations_total


def _is_api_spec_mapping(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    has_version = "openapi" in value or "swagger" in value
    has_paths = isinstance(value.get("paths"), dict)
    has_schema_section = isinstance(value.get("components"), dict) or isinstance(value.get("definitions"), dict)
    return has_version and has_paths and (has_schema_section or isinstance(value.get("info"), dict))


def _has_api_spec_text_hints(text: str) -> bool:
    has_version = re.search(r'(?mi)(?:^|[{\n,]\s*)["\']?(?:openapi|swagger)["\']?\s*:', text) is not None
    has_paths = re.search(r'(?mi)(?:^|[{\n,]\s*)["\']?paths["\']?\s*:', text) is not None
    has_schema_section = (
        re.search(r'(?mi)(?:^|[{\n,]\s*)["\']?components["\']?\s*:', text) is not None
        or re.search(r'(?mi)(?:^|[{\n,]\s*)["\']?definitions["\']?\s*:', text) is not None
    )
    return has_version and (has_paths or has_schema_section)


def _is_api_spec_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower_name = pure_path.name.lower()
    lower_parts = {part.lower() for part in pure_path.parts}
    suffix = pure_path.suffix.lower()

    if lower_name in _API_SPEC_FILENAMES:
        return True

    return suffix in {".json", ".yaml", ".yml"} and bool(lower_parts.intersection(_API_SPEC_PATH_PARTS))


def _is_lockfile_path(path: str) -> bool:
    return PurePosixPath(path).name.lower() in _LOCKFILE_NAMES


def _parse_yaml_like_keys(text: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []
    list_indexes: dict[str, int] = {}

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()

        parent_key = stack[-1][1] if stack else ""

        if stripped.startswith("-"):
            value_text = stripped[1:].strip()
            item_index = list_indexes.get(parent_key, 0)
            list_indexes[parent_key] = item_index + 1
            item_key = f"{parent_key}[{item_index}]" if parent_key else f"[{item_index}]"

            if not value_text:
                stack.append((indent, item_key))
                continue

            child_key, child_value = _split_yaml_key_value(value_text)
            if child_key is None:
                keys.append(
                    {
                        "key": item_key,
                        "value_kind": _yaml_value_kind(value_text),
                        "value_preview": _safe_preview(item_key, _strip_inline_comment(value_text)),
                        "line": line_number,
                    }
                )
                continue

            full_key = f"{item_key}.{child_key}"
            if child_value:
                keys.append(
                    {
                        "key": full_key,
                        "value_kind": _yaml_value_kind(child_value),
                        "value_preview": _safe_preview(full_key, _strip_inline_comment(child_value)),
                        "line": line_number,
                    }
                )
                stack.append((indent, item_key))
            else:
                stack.append((indent, full_key))
            continue

        key, value_text = _split_yaml_key_value(stripped)
        if key is None:
            continue

        full_key = f"{parent_key}.{key}" if parent_key else key
        if value_text:
            keys.append(
                {
                    "key": full_key,
                    "value_kind": _yaml_value_kind(value_text),
                    "value_preview": _safe_preview(full_key, _strip_inline_comment(value_text)),
                    "line": line_number,
                }
            )
        else:
            stack.append((indent, full_key))

    keys.sort(key=lambda item: item["key"])
    return keys


def _split_yaml_key_value(value: str) -> tuple[str | None, str | None]:
    match = re.match(r"^['\"]?([^:'\"]+)['\"]?\s*:\s*(.*)$", value)
    if match is None:
        return None, None

    key = match.group(1).strip()
    if not key:
        return None, None

    return key, match.group(2).strip()


def _parse_env_like_keys(text: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        if not key:
            continue

        keys.append(
            {
                "key": key,
                "value_kind": "string",
                "value_preview": _safe_preview(key, value.strip().strip("'\"")),
                "line": line_number,
            }
        )

    keys.sort(key=lambda item: item["key"])
    return keys


def _parse_properties_like_keys(text: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue

        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue

        key, value = line.split(separator, 1)
        key = key.strip()
        if not key:
            continue

        keys.append(
            {
                "key": key,
                "value_kind": "string",
                "value_preview": _safe_preview(key, value.strip()),
                "line": line_number,
            }
        )

    keys.sort(key=lambda item: item["key"])
    return keys


def _parse_ini_keys(text: str) -> list[dict[str, Any]]:
    parser = configparser.ConfigParser()
    parser.read_string(text)
    keys: list[dict[str, Any]] = []
    for section in sorted(parser.sections()):
        for key, value in sorted(parser[section].items()):
            full_key = f"{section}.{key}"
            keys.append(
                {
                    "key": full_key,
                    "value_kind": "string",
                    "value_preview": _safe_preview(full_key, value),
                    "line": None,
                }
            )

    return keys


def _dynamic_reference(
    source: dict[str, Any],
    *,
    kind: str,
    accessor: str,
    expression: str,
    reason: str,
) -> dict[str, Any]:
    return _with_finding_scope(
        {
            "kind": kind,
            "accessor": accessor,
            "expression": _compact_expression(expression),
            "reason": reason,
            "source": source,
            "confidence": "dynamic",
        },
        source,
    )


def _compact_expression(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _parse_call_args(line: str, open_paren_index: int) -> list[str]:
    if open_paren_index >= len(line) or line[open_paren_index] != "(":
        return []

    args: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False

    for char in line[open_paren_index + 1 :]:
        if quote is not None:
            current.append(char)
            if quote != "`" and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue

        if char in {'"', "'", "`"}:
            quote = char
            current.append(char)
            continue

        if char in "([{":
            depth += 1
            current.append(char)
            continue

        if char in ")]}":
            if depth == 0 and char == ")":
                arg = "".join(current).strip()
                if arg:
                    args.append(arg)
                return args
            depth = max(0, depth - 1)
            current.append(char)
            continue

        if char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue

        current.append(char)

    return []


def _split_top_level(value: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False

    for char in value:
        if quote is not None:
            current.append(char)
            if quote != "`" and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = None
            escaped = False
            continue

        if char in {'"', "'", "`"}:
            quote = char
            current.append(char)
            continue

        if char in "([{":
            depth += 1
            current.append(char)
            continue

        if char in ")]}":
            depth = max(0, depth - 1)
            current.append(char)
            continue

        if char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue

        current.append(char)

    if current:
        args.append("".join(current).strip())

    return [arg for arg in args if arg]


def _parse_go_literal(value: str | None) -> Any:
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    if len(text) >= 2 and text[0] == text[-1] == "`":
        return text[1:-1]

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        try:
            return json.loads(text) if text[0] == '"' else text[1:-1]
        except json.JSONDecodeError:
            return text[1:-1]

    if text == "true":
        return True
    if text == "false":
        return False

    try:
        return int(text)
    except ValueError:
        pass

    try:
        return float(text)
    except ValueError:
        return None


def _source_ref(
    path: str,
    line: int,
    source_index: dict[str, Any],
    *,
    end_line: int | None = None,
) -> dict[str, Any]:
    symbol = _symbol_at(path, line, source_index)
    source_scope = source_index["source_scopes_by_file"].get(path, SOURCE_SCOPE_RUNTIME)
    return {
        "file_path": path,
        "start_line": line,
        "end_line": end_line or line,
        "package": source_index["packages_by_file"].get(path),
        "symbol_id": symbol.get("symbol_id") if symbol else None,
        "symbol_qualified_name": symbol.get("qualified_name") if symbol else None,
        "source_scope": source_scope,
        "runtime_scope": runtime_scope_from_source_scope(source_scope),
    }


def _with_finding_scope(item: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    source_scope = source.get("source_scope", SOURCE_SCOPE_RUNTIME)
    return {
        **item,
        "source_scope": source_scope,
        "runtime_scope": runtime_scope_from_source_scope(source_scope),
    }


def _symbol_at(path: str, line: int, source_index: dict[str, Any]) -> dict[str, Any] | None:
    for symbol in source_index["symbols_by_file"].get(path, []):
        if symbol["start_line"] <= line <= symbol["end_line"]:
            return symbol

    return None


def _required_env_hint(lines: list[str], line_index: int, accessor: str, key: str) -> tuple[bool, str | None]:
    window = "\n".join(lines[line_index : min(len(lines), line_index + 6)]).lower()
    has_terminal_failure = any(token in window for token in ("panic(", "fatal", "return nil", "return \"\""))
    if accessor == "LookupEnv" and "!ok" in window and has_terminal_failure:
        return True, "lookup_env_failure_path"

    if accessor == "Getenv" and "== \"\"" in window and has_terminal_failure:
        return True, "empty_getenv_failure_path"

    current_line = lines[line_index].lower()
    if key.lower() in current_line and "required" in current_line:
        return True, "nearby_required_hint"

    return False, None


def _tag_is_required(tag_map: dict[str, str]) -> bool:
    required_value = tag_map.get("required")
    if required_value and required_value.lower() in {"true", "required", "1", "yes"}:
        return True

    validate_value = tag_map.get("validate")
    return bool(validate_value and "required" in validate_value.lower())


def _config_format(path: str) -> str | None:
    pure_path = PurePosixPath(path)
    name = pure_path.name.lower()
    suffix = pure_path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix in {".ini", ".cfg"}:
        return "ini"
    if suffix == ".properties":
        return "properties"
    if name == ".env" or name.startswith(".env."):
        return "dotenv"

    return None


def _value_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def _yaml_value_kind(value: str) -> str:
    normalized = _strip_inline_comment(value).strip().strip("'\"")
    if normalized.lower() in {"true", "false"}:
        return "bool"
    if normalized.lower() in {"null", "~"}:
        return "null"
    if normalized.startswith("["):
        return "array"
    if normalized.startswith("{"):
        return "object"
    try:
        float(normalized)
        return "number"
    except ValueError:
        return "string"


def _safe_preview(key: str, value: Any) -> str | None:
    if value is None or isinstance(value, dict | list):
        return None

    normalized_key = key.lower()
    if any(part in normalized_key for part in _REDACT_KEY_PARTS):
        return "<redacted>"

    preview = str(value).strip()
    if len(preview) > 128:
        return preview[:125] + "..."

    return preview


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    for index, char in enumerate(value):
        if quote is not None:
            if char == quote:
                quote = None
            continue

        if char in {'"', "'"}:
            quote = char
            continue

        if char == "#":
            return value[:index].rstrip()

    return value


def _is_vendor_path(path: str) -> bool:
    return "vendor" in {part.lower() for part in PurePosixPath(path).parts}
