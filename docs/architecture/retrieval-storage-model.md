# Retrieval Storage Model

## Purpose

`RAG-001` fixes the first retrieval storage contract for the rewritten
`ingestion_service`. The retrieval index is snapshot-bound and internal-only:
public domain APIs use `snapshot_id`, never Qdrant collection names or raw
payload details.

## Collection

- Collection: `code_chunks_v1`
- Ownership: `ingestion_service`
- Scope: all repositories and snapshots sharing the same payload schema version
- Vector name: `dense`
- Distance: `cosine`
- Default vector size: `896`

The collection is versioned by schema, not by repository. Reindexing and
retrieval must filter by `snapshot_id`.

## Payload

Required payload fields:

- `snapshot_id`
- `repository_id`
- `commit_sha`
- `file_path`
- `language`
- `kind`
- `chunk_kind`
- `is_test`
- `source_scope`
- `text`

Optional payload fields:

- `workspace_unit_id`
- `package`
- `package_id`
- `name`
- `start_line`
- `end_line`

`package` is a structured object for normalized source metadata. `package_id`
is duplicated as a flat field because it is a practical Qdrant filter/index
target.

## Payload Indexes

Create indexes for:

- `snapshot_id`
- `repository_id`
- `commit_sha`
- `file_path`
- `workspace_unit_id`
- `language`
- `package_id`
- `kind`
- `name`
- `chunk_kind`
- `is_test`
- `source_scope`

`snapshot_id` is mandatory for all retrieval calls. Downstream services should
not know the collection name and should call ingestion retrieval through an
internal endpoint.

