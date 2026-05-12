import logging
import time
from dataclasses import dataclass
from typing import Any

from app.retrieval.embeddings import EmbeddingProvider, EmbeddingProviderError
from app.retrieval.qdrant_store import (
    CodeChunkSearchFilters,
    CodeChunkSearchHit,
    QdrantCodeChunkStore,
    RetrievalIndexError,
)

logger = logging.getLogger(__name__)


class RetrievalSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievalSearchRequest:
    snapshot_id: str
    query: str
    top_k: int
    filters: CodeChunkSearchFilters
    score_threshold: float | None = None


@dataclass(frozen=True)
class RetrievalPackage:
    package_id: str | None
    name: str | None
    import_path: str | None
    dir_path: str | None
    module_path: str | None


@dataclass(frozen=True)
class RetrievalSource:
    repository_id: str
    snapshot_id: str
    commit_sha: str
    file_path: str
    language: str
    source_scope: str
    is_test: bool
    start_line: int | None
    end_line: int | None
    workspace_unit_id: str | None
    package: RetrievalPackage | None


@dataclass(frozen=True)
class RetrievalEntity:
    kind: str
    chunk_kind: str
    name: str | None
    symbol_id: str | None
    symbol_signature: str | None


@dataclass(frozen=True)
class RetrievalMatch:
    chunk_id: str
    score: float
    text: str
    source: RetrievalSource
    entity: RetrievalEntity


@dataclass(frozen=True)
class RetrievalSearchResult:
    snapshot_id: str
    query: str
    top_k: int
    elapsed_ms: float
    embedding_provider: str
    embedding_model: str
    matches: tuple[RetrievalMatch, ...]


class RetrievalSearcher:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        store: QdrantCodeChunkStore,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._store = store

    def search(self, request: RetrievalSearchRequest) -> RetrievalSearchResult:
        started_at = time.perf_counter()
        try:
            query_vector = self._embedding_provider.embed_query(request.query)
            hits = self._store.search_snapshot_chunks(
                snapshot_id=request.snapshot_id,
                query_vector=query_vector,
                limit=request.top_k,
                filters=request.filters,
                score_threshold=request.score_threshold,
            )
        except (EmbeddingProviderError, RetrievalIndexError):
            raise
        except Exception as exc:  # noqa: BLE001
            raise RetrievalSearchError(f"Retrieval search failed: {exc}") from exc

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        matches = tuple(_match_from_hit(hit) for hit in hits)
        logger.info(
            "Retrieval search completed snapshot_id=%s top_k=%s matches=%s elapsed_ms=%.2f provider=%s",
            request.snapshot_id,
            request.top_k,
            len(matches),
            elapsed_ms,
            self._embedding_provider.provider,
        )
        return RetrievalSearchResult(
            snapshot_id=request.snapshot_id,
            query=request.query,
            top_k=request.top_k,
            elapsed_ms=elapsed_ms,
            embedding_provider=self._embedding_provider.provider,
            embedding_model=self._embedding_provider.model,
            matches=matches,
        )


def _match_from_hit(hit: CodeChunkSearchHit) -> RetrievalMatch:
    payload = hit.payload
    return RetrievalMatch(
        chunk_id=_payload_str(payload, "chunk_id") or hit.point_id,
        score=hit.score,
        text=_payload_str(payload, "text") or "",
        source=RetrievalSource(
            repository_id=_payload_str(payload, "repository_id") or "",
            snapshot_id=_payload_str(payload, "snapshot_id") or "",
            commit_sha=_payload_str(payload, "commit_sha") or "",
            file_path=_payload_str(payload, "file_path") or "",
            language=_payload_str(payload, "language") or "unknown",
            source_scope=_payload_str(payload, "source_scope") or "unknown",
            is_test=bool(payload.get("is_test", False)),
            start_line=_payload_int(payload, "start_line"),
            end_line=_payload_int(payload, "end_line"),
            workspace_unit_id=_payload_str(payload, "workspace_unit_id"),
            package=_package_from_payload(payload.get("package"), _payload_str(payload, "package_id")),
        ),
        entity=RetrievalEntity(
            kind=_payload_str(payload, "kind") or "unknown",
            chunk_kind=_payload_str(payload, "chunk_kind") or "unknown",
            name=_payload_str(payload, "name"),
            symbol_id=_payload_str(payload, "symbol_id"),
            symbol_signature=_payload_str(payload, "symbol_signature"),
        ),
    )


def _package_from_payload(value: Any, package_id: str | None) -> RetrievalPackage | None:
    if not isinstance(value, dict) and not package_id:
        return None
    package = value if isinstance(value, dict) else {}
    return RetrievalPackage(
        package_id=_value_str(package.get("package_id")) or package_id,
        name=_value_str(package.get("name")),
        import_path=_value_str(package.get("import_path")),
        dir_path=_value_str(package.get("dir_path")),
        module_path=_value_str(package.get("module_path")),
    )


def _payload_str(payload: dict[str, Any], key: str) -> str | None:
    return _value_str(payload.get(key))


def _value_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _payload_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
