import configparser
import hashlib
import json
import re
import tomllib
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key

CONFIG_INVENTORY_ARTIFACT_KIND = "config_inventory"
CONFIG_INVENTORY_SCHEMA_VERSION = 1

_ENV_CALL_RE = re.compile(r"\b(?:os|syscall)\.(Getenv|LookupEnv)\s*\(")
_FLAG_CALL_RE = re.compile(
    r"\b(?:flag|pflag)\."
    r"(String|Bool|Int|Int64|Uint|Uint64|Float64|Duration|"
    r"StringVar|BoolVar|IntVar|Int64Var|UintVar|Uint64Var|Float64Var|DurationVar|Var)\s*\("
)
_STRUCT_START_RE = re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+struct\s*\{")
_STRUCT_TAG_RE = re.compile(r'([A-Za-z_]\w*):"([^"]*)"')
_CONFIG_TAGS = {"json", "yaml", "toml", "mapstructure", "env", "envconfig"}
_REDACT_KEY_PARTS = {"secret", "password", "passwd", "token", "apikey", "api_key", "private_key"}
_MAX_CONFIG_FILE_BYTES = 256 * 1024
_MAX_CONFIG_KEYS_PER_FILE = 256
_MAX_CONFIG_NESTING_DEPTH = 8
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

    env_vars, flags, config_structs = _scan_go_sources(repo_root, go_symbols, source_index)
    config_files, api_specs = _scan_config_files(repo_root, file_inventory)

    env_vars.sort(key=lambda item: (item["key"], item["source"]["file_path"], item["source"]["start_line"]))
    flags.sort(key=lambda item: (item["name"], item["source"]["file_path"], item["source"]["start_line"]))
    config_structs.sort(key=lambda item: (item["source"]["file_path"], item["source"]["start_line"], item["name"]))
    config_files.sort(key=lambda item: item["path"])
    api_specs.sort(key=lambda item: item["path"])

    config_file_keys_total = sum(len(item["keys"]) for item in config_files)
    config_files_truncated_total = sum(1 for item in config_files if item["truncated"])
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
    summary = {
        "env_vars_total": len(env_vars),
        "flags_total": len(flags),
        "config_structs_total": len(config_structs),
        "config_files_total": len(config_files),
        "config_file_keys_total": config_file_keys_total,
        "config_files_truncated_total": config_files_truncated_total,
        "api_specs_total": len(api_specs),
        "api_spec_kind_counts": dict(sorted(Counter(item["spec_kind"] for item in api_specs).items())),
        "configuration_items_total": len(env_vars) + len(flags) + len(config_structs) + config_file_keys_total,
        "required_items_total": required_items_total,
        "config_file_format_counts": dict(sorted(Counter(item["format"] for item in config_files).items())),
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
        "flags": flags,
        "config_structs": config_structs,
        "config_files": config_files,
        "api_specs": api_specs,
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
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    for symbol in go_symbols.get("symbols", []):
        symbols_by_file.setdefault(symbol["file_path"], []).append(symbol)

    for symbols in symbols_by_file.values():
        symbols.sort(key=lambda item: (item["start_line"], item["end_line"], item["qualified_name"]))

    return {"packages_by_file": packages_by_file, "symbols_by_file": symbols_by_file}


def _scan_go_sources(
    repo_root: Path,
    go_symbols: dict[str, Any],
    source_index: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    env_vars: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    config_structs: list[dict[str, Any]] = []

    for file_record in go_symbols.get("files", []):
        if file_record.get("is_vendor") or file_record.get("is_generated"):
            continue

        path = file_record["path"]
        source_path = repo_root / path
        text = source_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        env_vars.extend(_extract_env_vars(path, lines, source_index))
        flags.extend(_extract_flags(path, lines, source_index))
        config_structs.extend(_extract_config_structs(path, lines, source_index))

    return env_vars, flags, config_structs


def _extract_env_vars(path: str, lines: list[str], source_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for line_index, line in enumerate(lines):
        for match in _ENV_CALL_RE.finditer(line):
            args = _parse_call_args(line, match.end() - 1)
            if not args:
                continue

            key = _parse_go_literal(args[0])
            if not isinstance(key, str) or not key:
                continue

            required, required_reason = _required_env_hint(lines, line_index, match.group(1), key)
            findings.append(
                {
                    "key": key,
                    "accessor": f"os.{match.group(1)}",
                    "default_value": None,
                    "required": required,
                    "required_reason": required_reason,
                    "source": _source_ref(path, line_index + 1, source_index),
                }
            )

    return findings


def _extract_flags(path: str, lines: list[str], source_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for line_index, line in enumerate(lines):
        for match in _FLAG_CALL_RE.finditer(line):
            flag_type = match.group(1)
            args = _parse_call_args(line, match.end() - 1)
            parsed = _parse_flag_call(flag_type, args)
            if parsed is None:
                continue

            parsed["source"] = _source_ref(path, line_index + 1, source_index)
            findings.append(parsed)

    return findings


def _parse_flag_call(flag_type: str, args: list[str]) -> dict[str, Any] | None:
    is_var = flag_type.endswith("Var")
    is_custom_var = flag_type == "Var"
    if (is_var and len(args) < 4) or (is_custom_var and len(args) < 3) or (not is_var and len(args) < 3):
        return None

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
        return None

    usage = _parse_go_literal(usage_arg)
    default_value = _parse_go_literal(default_arg) if default_arg is not None else None
    required = isinstance(usage, str) and "required" in usage.lower()

    return {
        "name": name,
        "flag_type": flag_type.removesuffix("Var").lower(),
        "default_value": default_value,
        "default_value_raw": default_arg.strip() if default_arg is not None else None,
        "usage": usage if isinstance(usage, str) else usage_arg.strip(),
        "required": required,
        "required_reason": "usage_mentions_required" if required else None,
        "destination": destination,
    }


def _extract_config_structs(path: str, lines: list[str], source_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
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
            findings.append(
                {
                    "name": name,
                    "fields": fields,
                    "source": _source_ref(path, start_line, source_index, end_line=end_index + 1),
                }
            )

        index = end_index + 1

    return findings


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
        if not config_keys and not any(key in tag_map for key in {"default", "required", "validate"}):
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


def _scan_config_files(repo_root: Path, file_inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config_files: list[dict[str, Any]] = []
    api_specs: list[dict[str, Any]] = []

    for file_record in file_inventory.get("files", []):
        if file_record.get("is_binary"):
            continue

        path = file_record["path"]
        if _is_vendor_path(path):
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
            }
        )

    return config_files, api_specs


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
    title_match = re.search(r"(?mi)^\s*title\s*:\s*['\"]?([^'\"\n#]+)", text)
    app_version_match = re.search(r"(?mi)^\s*version\s*:\s*['\"]?([^'\"\n#]+)", text)
    paths_total, operations_total = _count_yaml_api_paths(text)

    spec_kind = version_match.group(1).lower() if version_match else "unknown"
    return {
        "spec_kind": spec_kind,
        "spec_version": version_match.group(2).strip() if version_match else None,
        "title": title_match.group(1).strip() if title_match else None,
        "version": app_version_match.group(1).strip() if app_version_match else None,
        "paths_total": paths_total,
        "operations_total": operations_total,
    }


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


def _parse_yaml_like_keys(text: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    stack: list[tuple[int, str]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        stripped = raw_line.strip()
        if stripped.startswith("- "):
            continue

        match = re.match(r"^(\s*)([A-Za-z0-9_.-]+)\s*:\s*(.*)$", raw_line)
        if match is None:
            continue

        indent = len(match.group(1))
        key = match.group(2)
        value_text = match.group(3).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()

        full_key = ".".join([item[1] for item in stack] + [key])
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
            stack.append((indent, key))

    keys.sort(key=lambda item: item["key"])
    return keys


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
        return text


def _source_ref(
    path: str,
    line: int,
    source_index: dict[str, Any],
    *,
    end_line: int | None = None,
) -> dict[str, Any]:
    symbol = _symbol_at(path, line, source_index)
    return {
        "file_path": path,
        "start_line": line,
        "end_line": end_line or line,
        "package": source_index["packages_by_file"].get(path),
        "symbol_id": symbol.get("symbol_id") if symbol else None,
        "symbol_qualified_name": symbol.get("qualified_name") if symbol else None,
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
