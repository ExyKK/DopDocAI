# Retrieval Storage Model

## Purpose

`RAG-001` fixed the first retrieval storage contract for the rewritten
`ingestion_service`; `RAG-002`/`RAG-003` add deterministic chunk construction
and snapshot replacement semantics; `RAG-004A` introduces an embedding provider
boundary so local dev can stay lightweight while quality indexing can use a
separate model container; `RAG-004B` adds an optional CUDA runtime for that same
container. The retrieval index is snapshot-bound and
internal-only: public domain APIs use `snapshot_id`, never Qdrant collection
names or raw payload details.

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

- `chunk_id`
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
- `symbol_id`
- `symbol_signature`

`package` is a structured object for normalized source metadata. `package_id`
is duplicated as a flat field because it is a practical Qdrant filter/index
target.

`chunk_id` is a deterministic UUIDv5 derived from:

- `snapshot_id`
- normalized `file_path`
- symbol signature, or `file:{path}` for plain text fallback chunks
- zero-based `chunk_index`

Go symbols are chunked as `chunk_kind=go_symbol` and retain `symbol_id` so
source artifact symbol records can be traced to one or more chunks. Text files
that are not represented by Go symbol chunks use bounded `file_slice` chunks.

## Embedding Providers

`ingestion_service` uses an internal `EmbeddingProvider` abstraction for both
document chunks and future retrieval queries.

- `hash`: default lightweight dev/smoke provider; deterministic, no model
  download, same configured vector size.
- `jina_http`: quality provider that calls optional `embedding_service`, which
  serves `jinaai/jina-code-embeddings-0.5b` in a separate container.

The default vector size remains `896`, matching `jina-code-embeddings-0.5b` and
the existing `code_chunks_v1` collection. Provider metadata is recorded in
`index_runs.StatsJson`: `embedding_provider`, `embedding_model`,
`embedding_dimension`, `embedding_batches_total` and `embedding_inputs_total`.

The model container has two runtime shapes:

- `embeddings`: CPU profile for correctness checks when GPU is unavailable.
- `embeddings` plus `docker-compose.embeddings.cuda.yml`: the same
  `embedding_service` switched to `Dockerfile.cuda`, `EMBED_DEVICE=cuda` and a
  Docker Compose NVIDIA GPU reservation. The worker still talks to the same
  `jina_http` provider URL, so retrieval/indexing code does not depend on
  whether the model runs on CPU or GPU.

## Payload Indexes

Create indexes for:

- `chunk_id`
- `snapshot_id`
- `repository_id`
- `commit_sha`
- `file_path`
- `workspace_unit_id`
- `language`
- `package_id`
- `kind`
- `name`
- `symbol_id`
- `chunk_kind`
- `is_test`
- `source_scope`

`snapshot_id` is mandatory for all retrieval calls. Downstream services should
not know the collection name and should call ingestion retrieval through an
internal endpoint.

## Snapshot Replacement

Indexing a snapshot performs a full replace for that snapshot:

1. Ensure `code_chunks_v1` and payload indexes exist.
2. Count and delete existing points with `snapshot_id`.
3. Batch upsert deterministic chunk ids and vectors.
4. Record counters on `index_runs`: built chunks, deleted stale points, batches,
   and upserted vectors.

This means retrying or reindexing the same snapshot does not accumulate stale
chunks.

## Internal Search API

`RAG-004` exposes retrieval through `ingestion_service`, not directly through
Qdrant:

- Route: `POST /internal/v1/retrieval/search`
- Required request fields: `snapshot_id`, `query`
- Optional request fields: `top_k`, `score_threshold`, `filters`
- Response: normalized matches with `score`, `dense_score`,
  `score_breakdown`, `text`, `source` and `entity` fields.

Supported filters:

- `workspace_unit_ids`
- `languages`
- `source_scopes`
- `chunk_kinds`
- `package_ids`
- `file_paths`
- `include_tests`

The endpoint embeds the query through the configured `EmbeddingProvider`,
searches `code_chunks_v1` with a mandatory `snapshot_id` filter, and returns
source DTOs. It does not expose collection names, vector names or raw Qdrant
point structures to downstream services.

`RAG-005` adds a lightweight hybrid layer over dense search:

1. Analyze the user query for path-like hints, symbol-like identifiers and
   lexical terms.
2. Expand the embedding query with extracted symbol/path hints.
3. Fetch a larger dense candidate set from Qdrant.
4. Rerank candidates with deterministic boosts from payload metadata:
   `file_path`, `name`, `symbol_signature`, `package_id`,
   `workspace_unit_id`, `source_scope`, `chunk_kind` and `text`.
5. Return only the requested `top_k` matches, including score breakdowns for
   observability.

Those payload fields are derived from `project_model`, `go_symbols`,
`package_graph` and file inventory artifacts during indexing. The hybrid layer
therefore improves symbol/path questions without requiring downstream services
to load raw artifacts or know the Qdrant schema.
