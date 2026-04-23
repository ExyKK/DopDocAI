from dataclasses import dataclass
from typing import Any


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
