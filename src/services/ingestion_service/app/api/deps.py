from functools import lru_cache

from app.core.config import settings
from app.infra.treesitter_client import TreeSitterManager
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.provider_factory import create_embedding_provider
from app.retrieval.qdrant_store import QdrantCodeChunkStore
from app.retrieval.search import RetrievalSearcher


@lru_cache
def get_treesitter() -> TreeSitterManager:
    return TreeSitterManager()


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return create_embedding_provider(settings)


@lru_cache
def get_code_chunk_store() -> QdrantCodeChunkStore:
    return QdrantCodeChunkStore(
        url=str(settings.qdrant_url),
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_code_chunks_collection,
        vector_size=settings.embedding_vector_size,
        batch_size=settings.qdrant_upsert_batch_size,
    )


@lru_cache
def get_retrieval_searcher() -> RetrievalSearcher:
    return RetrievalSearcher(
        embedding_provider=get_embedding_provider(),
        store=get_code_chunk_store(),
    )
