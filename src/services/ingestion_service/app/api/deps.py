from functools import lru_cache

from app.core.config import settings
from app.infra.qdrant_client import QdrantManager
from app.infra.treesitter_client import TreeSitterManager
from app.pipeline.embedder import Embedder


@lru_cache
def get_treesitter() -> TreeSitterManager:
    return TreeSitterManager()


@lru_cache
def get_embedder() -> Embedder:
    # heavy init once per process
    return Embedder(model_name=settings.jina_model)


def get_qdrant(collection_name: str) -> QdrantManager:
    return QdrantManager(
        url=str(settings.qdrant_url),
        api_key=settings.qdrant_api_key,
        collection_name=collection_name,
        batch_size=settings.qdrant_batch_size,
    )
