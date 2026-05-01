from dataclasses import dataclass
from typing import Any


def analysis_artifact_storage_key(
    *,
    repository_id: str,
    snapshot_id: str,
    artifact_kind: str,
    schema_version: int,
) -> str:
    return (
        f"repositories/{repository_id}/snapshots/{snapshot_id}/analysis/"
        f"{artifact_kind}.schema-v{schema_version}.json"
    )


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
    summary: dict[str, Any] | None = None
