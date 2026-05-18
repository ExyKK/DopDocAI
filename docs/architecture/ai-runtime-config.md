# AI Runtime Configuration

`CONFIG-001` makes the production-like AI runtime the default. Real LLM and
real embedding providers are enabled unless a lightweight mode is explicitly
selected.

## Primary Variables

Use central `DOPDOC_*` variables in the root `.env`:

```env
DOPDOC_LLM_PROVIDER=openrouter
DOPDOC_LLM_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
DOPDOC_LLM_API_KEY=
DOPDOC_LLM_MODEL=deepseek/deepseek-v3.2

DOPDOC_EMBEDDING_PROVIDER=jina_http
DOPDOC_EMBEDDING_MODEL=jinaai/jina-code-embeddings-0.5b
DOPDOC_EMBEDDING_VECTOR_SIZE=896
DOPDOC_EMBEDDING_SERVICE_URL=http://embedding_service:19400
```

## Lightweight Modes

Use these only for smoke runs or dependency-light development:

```env
DOPDOC_LLM_PROVIDER=stub
DOPDOC_EMBEDDING_PROVIDER=hash
```

`stub` avoids external LLM calls. `hash` keeps deterministic vector behavior
without loading the embedding model. These modes are intentionally opt-in so
manual tests exercise the same contracts as the real system by default.

## Compose Notes

The default `docker-compose.yml` maps central `DOPDOC_*` values into the
native settings consumed by Python and C# services. User-facing compose
configuration should stay on `DOPDOC_*`; service-local variables are an internal
adapter detail.

`embedding_service` is part of the default compose stack and uses the CUDA image
by default. A full quality indexing run should include:

```bash
docker compose up -d \
  postgres qdrant minio minio_init repository_service embedding_service ingestion_worker
```

CUDA tuning is controlled by the embedding runtime variables:

```env
EMBED_GPU_BATCH_SIZE=4
EMBED_TORCH_DTYPE=float16
EMBED_MAX_SEQ_LENGTH=1024
NVIDIA_VISIBLE_DEVICES=all
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```
