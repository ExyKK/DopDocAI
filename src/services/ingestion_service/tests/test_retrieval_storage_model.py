from app.retrieval.storage_model import (
    CODE_CHUNKS_COLLECTION,
    CODE_CHUNKS_DISTANCE,
    CODE_CHUNKS_SCHEMA_VERSION,
    CODE_CHUNKS_VECTOR_NAME,
    DEFAULT_CODE_CHUNKS_VECTOR_SIZE,
    payload_field_names,
    payload_index_field_names,
    qdrant_snapshot_filter,
    required_payload_field_names,
)


def test_code_chunks_v1_storage_contract_names_collection_by_schema_version() -> None:
    assert CODE_CHUNKS_COLLECTION == "code_chunks_v1"
    assert CODE_CHUNKS_SCHEMA_VERSION == 1
    assert CODE_CHUNKS_VECTOR_NAME == "dense"
    assert CODE_CHUNKS_DISTANCE == "cosine"
    assert DEFAULT_CODE_CHUNKS_VECTOR_SIZE == 896


def test_code_chunks_v1_payload_fields_cover_snapshot_bound_sources() -> None:
    fields = set(payload_field_names())
    required = set(required_payload_field_names())

    assert {
        "chunk_id",
        "snapshot_id",
        "repository_id",
        "commit_sha",
        "file_path",
        "language",
        "workspace_unit_id",
        "package",
        "kind",
        "name",
        "start_line",
        "end_line",
        "symbol_id",
        "symbol_signature",
        "chunk_kind",
        "is_test",
    } <= fields
    assert {
        "chunk_id",
        "snapshot_id",
        "repository_id",
        "commit_sha",
        "file_path",
        "language",
        "kind",
        "chunk_kind",
        "is_test",
        "source_scope",
        "text",
    } <= required


def test_code_chunks_v1_payload_indexes_support_snapshot_filtered_retrieval() -> None:
    indexes = set(payload_index_field_names())

    assert "snapshot_id" in indexes
    assert {
        "chunk_id",
        "repository_id",
        "commit_sha",
        "file_path",
        "workspace_unit_id",
        "language",
        "package_id",
        "kind",
        "name",
        "symbol_id",
        "chunk_kind",
        "is_test",
        "source_scope",
    } <= indexes
    assert qdrant_snapshot_filter("snapshot-1") == {
        "must": [
            {
                "key": "snapshot_id",
                "match": {
                    "value": "snapshot-1",
                },
            }
        ]
    }
