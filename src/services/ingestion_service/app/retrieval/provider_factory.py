from app.core.config import Settings
from app.retrieval.embeddings import EmbeddingProvider, HashEmbeddingProvider, HttpEmbeddingProvider


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "hash":
        return HashEmbeddingProvider(
            dimension=settings.embedding_vector_size,
            batch_size=settings.embedding_batch_size,
            document_prefix=settings.embedding_document_prefix,
            query_prefix=settings.embedding_query_prefix,
        )

    if settings.embedding_provider == "jina_http":
        return HttpEmbeddingProvider(
            base_url=str(settings.embedding_service_url),
            model=settings.embedding_model,
            dimension=settings.embedding_vector_size,
            batch_size=settings.embedding_batch_size,
            timeout_s=settings.embedding_request_timeout_s,
            max_attempts=settings.embedding_max_attempts,
            retry_delay_s=settings.embedding_retry_delay_s,
            document_prefix=settings.embedding_document_prefix,
            query_prefix=settings.embedding_query_prefix,
        )

    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")
