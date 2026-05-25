# AI Runtime Configuration

`CONFIG-001` makes the production-like AI runtime the default. Real LLM and
real embedding providers are enabled unless a lightweight mode is explicitly
selected.

The current primary LLM is `deepseek/deepseek-v4-flash` through OpenRouter. It
has a 1,048,576-token context window, so documentation evidence budgets are
spacious by default while still bounded and debuggable.

## Primary Variables

Use central `DOPDOC_*` variables in the root `.env`:

```env
DOPDOC_LLM_PROVIDER=openrouter
DOPDOC_LLM_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
DOPDOC_LLM_API_KEY=
DOPDOC_LLM_MODEL=deepseek/deepseek-v4-flash
DOPDOC_LLM_TEMPERATURE=0.2
DOPDOC_LLM_MAX_TOKENS=1536
DOPDOC_LLM_TOP_P=0.95
DOPDOC_LLM_REPETITION_PENALTY=1.05
DOPDOC_LLM_OPENROUTER_SITE_URL=http://localhost
DOPDOC_LLM_OPENROUTER_APP_TITLE=DopDocAI
DOPDOC_LLM_PROVIDER_OPTIONS_JSON=
DOPDOC_LLM_PROVIDER_MAX_PRICE_PROMPT=
DOPDOC_LLM_PROVIDER_MAX_PRICE_COMPLETION=

DOPDOC_DOCS_LLM_MAX_TOKENS=4096
DOPDOC_DOCS_OUTPUT_LANGUAGE=ru
DOPDOC_DOCS_EVIDENCE_PACK_MAX_TOKENS=120000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCE_TOKENS=16000
DOPDOC_DOCS_EVIDENCE_PACK_MAX_SOURCES=80
DOPDOC_DOCS_VERIFICATION_MODE=hybrid
DOPDOC_DOCS_MAX_REPAIR_ROUNDS=2
DOPDOC_DOCS_LLM_CALL_MAX_ATTEMPTS=3
DOPDOC_DOCS_LLM_CALL_RETRY_DELAY_S=1
DOPDOC_DOCS_LLM_JSON_MODE_ENABLED=true
DOPDOC_DOCS_PIPELINE_TRACE_ENABLED=true
DOPDOC_DOCS_LOG_LEVEL=INFO

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

`documentation_service` uses `DOPDOC_DOCS_LLM_MAX_TOKENS` for section output
length, while ChatService keeps the shared `DOPDOC_LLM_MAX_TOKENS` default.
Judge calls use JSON object mode by default, and generation/judge/repair LLM
calls retry locally before the job-level retry is used. Trace artifacts are also
on by default for manual debugging. For OpenRouter routing experiments, put a
JSON provider object into `DOPDOC_LLM_PROVIDER_OPTIONS_JSON`, for example
`{"sort":"throughput"}`, and use the max price knobs to produce
`provider.max_price`.
