from functools import lru_cache

from app.infra.treesitter_client import TreeSitterManager


@lru_cache
def get_treesitter() -> TreeSitterManager:
    return TreeSitterManager()
