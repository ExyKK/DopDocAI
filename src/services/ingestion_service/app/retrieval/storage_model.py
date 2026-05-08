from dataclasses import dataclass
from typing import Any

CODE_CHUNKS_COLLECTION = "code_chunks_v1"
CODE_CHUNKS_SCHEMA_VERSION = 1
CODE_CHUNKS_VECTOR_NAME = "dense"
CODE_CHUNKS_DISTANCE = "cosine"
DEFAULT_CODE_CHUNKS_VECTOR_SIZE = 896


@dataclass(frozen=True)
class PayloadField:
    name: str
    value_type: str
    required: bool
    description: str


@dataclass(frozen=True)
class PayloadIndex:
    field_name: str
    field_schema: str
    purpose: str


CODE_CHUNK_PAYLOAD_FIELDS: tuple[PayloadField, ...] = (
    PayloadField("chunk_id", "keyword", True, "Deterministic logical chunk UUID."),
    PayloadField("snapshot_id", "keyword", True, "Snapshot UUID; primary retrieval filter."),
    PayloadField("repository_id", "keyword", True, "Repository UUID for isolation and diagnostics."),
    PayloadField("commit_sha", "keyword", True, "Git commit SHA represented by the snapshot."),
    PayloadField("file_path", "keyword", True, "Repository-relative source file path."),
    PayloadField("language", "keyword", True, "Language or file kind used by retrieval filters."),
    PayloadField("workspace_unit_id", "keyword", False, "Project-model workspace owner, when known."),
    PayloadField("package", "object", False, "Language package metadata, such as Go package id/name/import path."),
    PayloadField("package_id", "keyword", False, "Denormalized package id for Qdrant filtering."),
    PayloadField("kind", "keyword", True, "Source entity kind, for example symbol, file, config, or artifact."),
    PayloadField("name", "keyword", False, "Symbol/entity name when the chunk is entity-scoped."),
    PayloadField("start_line", "integer", False, "1-based inclusive source start line."),
    PayloadField("end_line", "integer", False, "1-based inclusive source end line."),
    PayloadField("symbol_id", "keyword", False, "Source artifact symbol id linked to this chunk, when any."),
    PayloadField("symbol_signature", "keyword", False, "Stable symbol signature used for chunk id derivation."),
    PayloadField("chunk_kind", "keyword", True, "Chunk construction strategy, such as symbol, file_slice, or artifact_slice."),
    PayloadField("is_test", "bool", True, "Whether the source chunk belongs to test scope."),
    PayloadField("source_scope", "keyword", True, "Runtime/test/generated/docs/infra/vendor source scope."),
    PayloadField("text", "text", True, "Chunk text returned by internal retrieval APIs."),
)

CODE_CHUNK_PAYLOAD_INDEXES: tuple[PayloadIndex, ...] = (
    PayloadIndex("chunk_id", "keyword", "Logical chunk lookup and diagnostics."),
    PayloadIndex("snapshot_id", "keyword", "Mandatory filter for all retrieval calls."),
    PayloadIndex("repository_id", "keyword", "Repository isolation and cleanup diagnostics."),
    PayloadIndex("commit_sha", "keyword", "Snapshot/debug lookup by commit."),
    PayloadIndex("file_path", "keyword", "Path filters and source lookups."),
    PayloadIndex("workspace_unit_id", "keyword", "Service/frontend/docs scoped retrieval."),
    PayloadIndex("language", "keyword", "Language scoped retrieval."),
    PayloadIndex("package_id", "keyword", "Package scoped retrieval without nested-object filters."),
    PayloadIndex("kind", "keyword", "Entity kind filters."),
    PayloadIndex("name", "keyword", "Symbol/entity name filters."),
    PayloadIndex("symbol_id", "keyword", "Trace retrieval chunks back to source symbols."),
    PayloadIndex("chunk_kind", "keyword", "Chunk strategy filters."),
    PayloadIndex("is_test", "bool", "Exclude tests by default or include them explicitly."),
    PayloadIndex("source_scope", "keyword", "Runtime/generated/docs/infra scoped retrieval."),
)


def payload_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in CODE_CHUNK_PAYLOAD_FIELDS)


def required_payload_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in CODE_CHUNK_PAYLOAD_FIELDS if field.required)


def payload_index_field_names() -> tuple[str, ...]:
    return tuple(index.field_name for index in CODE_CHUNK_PAYLOAD_INDEXES)


def qdrant_snapshot_filter(snapshot_id: str) -> dict[str, Any]:
    return {
        "must": [
            {
                "key": "snapshot_id",
                "match": {
                    "value": snapshot_id,
                },
            }
        ]
    }
