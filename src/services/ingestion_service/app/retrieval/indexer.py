from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact
from app.retrieval.chunks import build_code_chunks
from app.retrieval.embeddings import EmbeddingBatch, EmbeddingProvider
from app.retrieval.qdrant_store import QdrantCodeChunkStore, SnapshotReplaceResult
from app.retrieval.storage_model import CODE_CHUNKS_VECTOR_NAME


@dataclass(frozen=True)
class RetrievalIndexResult:
    chunks_total: int
    deleted_points: int
    upserted_points: int
    batches_total: int
    stats: dict[str, Any]


class CodeChunkIndexer:
    def __init__(self, *, store: QdrantCodeChunkStore, embedding_provider: EmbeddingProvider) -> None:
        self._store = store
        self._embedding_provider = embedding_provider

    def rebuild_snapshot_index(
        self,
        repo_path: str | Path,
        *,
        repository_id: str,
        snapshot_id: str,
        snapshot_metadata: dict[str, Any],
        artifacts: tuple[BuiltAnalysisArtifact, ...],
        report_progress: Callable[..., None],
        ensure_alive: Callable[[], None],
    ) -> RetrievalIndexResult:
        report_progress(
            "building_retrieval_chunks",
            98,
            "Building deterministic retrieval chunks.",
            payload={"snapshot_id": snapshot_id},
        )
        chunk_result = build_code_chunks(
            repo_path,
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            snapshot_metadata=snapshot_metadata,
            artifacts=artifacts,
        )
        ensure_alive()

        report_progress(
            "embedding_retrieval_chunks",
            98,
            "Embedding retrieval chunks.",
            progress_current=0,
            progress_total=chunk_result.stats["chunks_total"],
            payload={
                "snapshot_id": snapshot_id,
                "chunks_total": chunk_result.stats["chunks_total"],
                "embedding_provider": self._embedding_provider.provider,
                "embedding_model": self._embedding_provider.model,
            },
        )
        embedding_batch = self._embedding_provider.embed_documents(
            [chunk.text for chunk in chunk_result.chunks]
        )
        ensure_alive()

        report_progress(
            "upserting_retrieval_chunks",
            99,
            "Replacing snapshot retrieval chunks in Qdrant.",
            progress_current=0,
            progress_total=chunk_result.stats["chunks_total"],
            payload={
                "snapshot_id": snapshot_id,
                "chunks_total": chunk_result.stats["chunks_total"],
                "collection": self._store.collection_name,
            },
        )
        replace_result = self._store.replace_snapshot_chunks(
            snapshot_id=snapshot_id,
            chunks=chunk_result.chunks,
            vectors=embedding_batch.vectors,
        )
        ensure_alive()

        stats = _index_stats(chunk_result.stats, replace_result, embedding_batch)
        report_progress(
            "upserting_retrieval_chunks",
            99,
            "Replaced snapshot retrieval chunks in Qdrant.",
            progress_current=replace_result.upserted_points,
            progress_total=replace_result.chunks_total,
            payload=stats,
        )
        ensure_alive()

        return RetrievalIndexResult(
            chunks_total=replace_result.chunks_total,
            deleted_points=replace_result.deleted_points,
            upserted_points=replace_result.upserted_points,
            batches_total=replace_result.batches_total,
            stats=stats,
        )


def _index_stats(
    chunk_stats: dict[str, Any],
    replace_result: SnapshotReplaceResult,
    embedding_batch: EmbeddingBatch,
) -> dict[str, Any]:
    return {
        **chunk_stats,
        "collection": replace_result.collection_name,
        "vector_name": CODE_CHUNKS_VECTOR_NAME,
        "vector_size": replace_result.vector_size,
        "embedding_provider": embedding_batch.provider,
        "embedding_model": embedding_batch.model,
        "embedding_dimension": embedding_batch.dimension,
        "embedding_batches_total": embedding_batch.batches_total,
        "embedding_inputs_total": embedding_batch.inputs_total,
        "deleted_points": replace_result.deleted_points,
        "upserted_points": replace_result.upserted_points,
        "batches_total": replace_result.batches_total,
    }
