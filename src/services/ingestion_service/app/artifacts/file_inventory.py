import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from git import Repo

from app.worker.snapshot_resolver import list_head_tree_files

FILE_INVENTORY_ARTIFACT_KIND = "file_inventory"
FILE_INVENTORY_SCHEMA_VERSION = 1

_MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdx", ".rst", ".txt"}
_CONFIG_EXTENSIONS = {
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".properties",
    ".xml",
}
_CONFIG_FILENAMES = {"dockerfile", "makefile", ".gitignore", ".editorconfig", ".env", ".env.example"}


@dataclass(frozen=True)
class BuiltAnalysisArtifact:
    artifact_kind: str
    schema_version: int
    format: str
    content_type: str
    storage_key: str
    checksum_sha256: str
    size_bytes: int
    row_count: int
    payload: bytes


def build_file_inventory_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
) -> BuiltAnalysisArtifact:
    repo_root = Path(repo_path)
    repo = Repo(repo_root)
    files: list[dict[str, Any]] = []
    kinds = Counter()

    for entry in list_head_tree_files(repo):
        file_path = repo_root / entry.path
        raw = file_path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        is_binary = _is_binary(raw)
        line_count = 0 if is_binary else _count_lines(raw)

        file_kind, flags = _classify_file(entry.path, raw, is_binary)
        kinds[file_kind] += 1

        files.append(
            {
                "path": entry.path,
                "kind": file_kind,
                "sha256": sha256,
                "size_bytes": entry.size,
                "line_count": line_count,
                "is_binary": is_binary,
                **flags,
            }
        )

    document = {
        "artifact_kind": FILE_INVENTORY_ARTIFACT_KIND,
        "schema_version": FILE_INVENTORY_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": {
            "files_total": len(files),
            "go_files_total": snapshot_metadata["go_files_total"],
            "readme_files_total": snapshot_metadata["readme_files_total"],
            "bytes_total": snapshot_metadata["bytes_total"],
            "kind_counts": dict(sorted(kinds.items())),
        },
        "files": files,
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=FILE_INVENTORY_ARTIFACT_KIND,
        schema_version=FILE_INVENTORY_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=(
            f"repositories/{repository_id}/snapshots/{snapshot_id}/analysis/"
            f"{FILE_INVENTORY_ARTIFACT_KIND}.schema-v{FILE_INVENTORY_SCHEMA_VERSION}.json"
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=len(files),
        payload=payload,
    )


def _classify_file(path: str, raw: bytes, is_binary: bool) -> tuple[str, dict[str, bool]]:
    pure_path = PurePosixPath(path)
    lower_path = path.lower()
    lower_name = pure_path.name.lower()
    parts = {part.lower() for part in pure_path.parts}

    is_vendor = "vendor" in parts
    is_generated = _is_generated(lower_name, raw)
    is_test = _is_test(lower_name, parts)

    if is_binary:
        kind = "binary"
    elif is_vendor:
        kind = "vendor"
    elif is_generated:
        kind = "generated"
    elif is_test:
        kind = "test"
    elif lower_path.endswith(".go"):
        kind = "go"
    elif pure_path.suffix.lower() in _MARKDOWN_EXTENSIONS or lower_name.startswith("readme"):
        kind = "markdown"
    elif pure_path.suffix.lower() in _CONFIG_EXTENSIONS or lower_name in _CONFIG_FILENAMES or lower_name.startswith("docker-compose"):
        kind = "config"
    else:
        kind = "other"

    return kind, {
        "is_generated": is_generated,
        "is_test": is_test,
        "is_vendor": is_vendor,
    }


def _is_binary(raw: bytes) -> bool:
    if not raw:
        return False

    sample = raw[:1024]
    if b"\0" in sample:
        return True

    nontext = sum(1 for byte in sample if byte < 9 or 13 < byte < 32)
    return (nontext / max(1, len(sample))) > 0.3


def _count_lines(raw: bytes) -> int:
    if not raw:
        return 0

    lines = raw.count(b"\n")
    if not raw.endswith(b"\n"):
        lines += 1
    return lines


def _is_generated(name: str, raw: bytes) -> bool:
    if name.endswith(".pb.go") or ".generated." in name or name.endswith("_generated.go") or name.endswith(".gen.go"):
        return True

    sample = raw[:4096].lower()
    return b"code generated" in sample or b"do not edit" in sample


def _is_test(name: str, parts: set[str]) -> bool:
    if name.endswith("_test.go") or name.startswith("test_") or ".spec." in name or ".test." in name:
        return True

    return "test" in parts or "tests" in parts
