import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from git import Repo

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key
from app.infra.treesitter_client import TreeSitterManager
from app.worker.snapshot_resolver import list_head_tree_files

GO_SYMBOLS_ARTIFACT_KIND = "go_symbols"
GO_SYMBOLS_SCHEMA_VERSION = 1


def build_go_symbols_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    treesitter: TreeSitterManager | None = None,
) -> BuiltAnalysisArtifact:
    repo_root = Path(repo_path)
    repo = Repo(repo_root)
    treesitter = treesitter or TreeSitterManager()

    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    kind_counts = Counter()
    packages: set[str] = set()
    files_with_symbols_total = 0
    files_with_parse_errors_total = 0

    for entry in list_head_tree_files(repo):
        if not entry.path.lower().endswith(".go"):
            continue

        file_path = repo_root / entry.path
        text = file_path.read_text(encoding="utf-8", errors="replace")
        parsed = treesitter.extract_go_file(text, entry.path)

        if parsed.package:
            packages.add(parsed.package)

        if parsed.parse_error:
            files_with_parse_errors_total += 1

        file_record = {
            "path": parsed.path,
            "package": parsed.package,
            "imports": [
                {
                    "path": spec.path,
                    "name": spec.name,
                    "is_dot": spec.is_dot,
                    "is_blank": spec.is_blank,
                }
                for spec in parsed.imports
            ],
            "is_generated": parsed.is_generated,
            "is_test": parsed.is_test,
            "is_vendor": parsed.is_vendor,
            "parse_error": parsed.parse_error,
            "symbols_total": len(parsed.symbols),
        }
        files.append(file_record)

        if parsed.symbols:
            files_with_symbols_total += 1

        for symbol in parsed.symbols:
            kind_counts[symbol.kind] += 1
            symbols.append(
                {
                    "symbol_id": symbol.symbol_id,
                    "kind": symbol.kind,
                    "name": symbol.name,
                    "qualified_name": symbol.qualified_name,
                    "package": symbol.package,
                    "file_path": parsed.path,
                    "signature": symbol.signature,
                    "doc_comment": symbol.doc_comment,
                    "type_parameters": symbol.type_parameters,
                    "receiver": (
                        {
                            "text": symbol.receiver.text,
                            "type": symbol.receiver.type_text,
                            "base_type": symbol.receiver.base_type,
                            "is_pointer": symbol.receiver.is_pointer,
                        }
                        if symbol.receiver is not None
                        else None
                    ),
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                    "exported": symbol.exported,
                    "is_alias": symbol.is_alias,
                    "is_generated": parsed.is_generated,
                    "is_test": parsed.is_test,
                    "is_vendor": parsed.is_vendor,
                }
            )

    files.sort(key=lambda item: item["path"])
    symbols.sort(
        key=lambda item: (
            item["file_path"],
            item["start_line"],
            item["end_line"],
            item["kind"],
            item["qualified_name"],
        )
    )

    summary = {
        "go_files_total": snapshot_metadata["go_files_total"],
        "files_with_symbols_total": files_with_symbols_total,
        "files_with_parse_errors_total": files_with_parse_errors_total,
        "packages_total": len(packages),
        "symbols_total": len(symbols),
        "kind_counts": dict(sorted(kind_counts.items())),
    }

    document = {
        "artifact_kind": GO_SYMBOLS_ARTIFACT_KIND,
        "schema_version": GO_SYMBOLS_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": summary,
        "files": files,
        "symbols": symbols,
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=GO_SYMBOLS_ARTIFACT_KIND,
        schema_version=GO_SYMBOLS_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=analysis_artifact_storage_key(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            artifact_kind=GO_SYMBOLS_ARTIFACT_KIND,
            schema_version=GO_SYMBOLS_SCHEMA_VERSION,
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=len(symbols),
        payload=payload,
        summary=summary,
    )
