from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.retrieval.chunks import CodeChunk
from app.retrieval.storage_model import (
    CODE_CHUNK_PAYLOAD_INDEXES,
    CODE_CHUNKS_DISTANCE,
    CODE_CHUNKS_VECTOR_NAME,
)


class RetrievalIndexError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotReplaceResult:
    collection_name: str
    chunks_total: int
    deleted_points: int
    upserted_points: int
    batches_total: int
    vector_size: int


@dataclass(frozen=True)
class CodeChunkSearchFilters:
    workspace_unit_ids: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    source_scopes: tuple[str, ...] = ()
    chunk_kinds: tuple[str, ...] = ()
    package_ids: tuple[str, ...] = ()
    file_paths: tuple[str, ...] = ()
    include_tests: bool = True


@dataclass(frozen=True)
class CodeChunkSearchHit:
    point_id: str
    score: float
    payload: dict[str, Any]


class QdrantCodeChunkStore:
    def __init__(
        self,
        *,
        url: str,
        api_key: str | None,
        collection_name: str,
        vector_size: int,
        batch_size: int = 64,
        client: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")

        self.collection_name = collection_name
        self.vector_size = vector_size
        self.batch_size = batch_size
        self._client = client or QdrantClient(url=url, api_key=api_key)

    def replace_snapshot_chunks(
        self,
        *,
        snapshot_id: str,
        chunks: tuple[CodeChunk, ...],
        vectors: tuple[list[float], ...],
    ) -> SnapshotReplaceResult:
        if len(chunks) != len(vectors):
            raise ValueError(f"Chunk/vector count mismatch: {len(chunks)} chunks, {len(vectors)} vectors.")

        try:
            self.ensure_collection()
            deleted_points = self.delete_snapshot(snapshot_id)
            batches_total = 0
            for batch in _batches(tuple(zip(chunks, vectors, strict=True)), self.batch_size):
                points = [
                    models.PointStruct(
                        id=chunk.chunk_id,
                        vector={CODE_CHUNKS_VECTOR_NAME: vector},
                        payload=chunk.payload,
                    )
                    for chunk, vector in batch
                ]
                self._client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
                batches_total += 1
        except Exception as exc:  # noqa: BLE001
            raise RetrievalIndexError(f"Qdrant code chunk indexing failed: {exc}") from exc

        return SnapshotReplaceResult(
            collection_name=self.collection_name,
            chunks_total=len(chunks),
            deleted_points=deleted_points,
            upserted_points=len(chunks),
            batches_total=batches_total,
            vector_size=self.vector_size,
        )

    def ensure_collection(self) -> None:
        if not self._client.collection_exists(self.collection_name):
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    CODE_CHUNKS_VECTOR_NAME: models.VectorParams(
                        size=self.vector_size,
                        distance=_distance(),
                    )
                },
            )

        for index in CODE_CHUNK_PAYLOAD_INDEXES:
            try:
                self._client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=index.field_name,
                    field_schema=_payload_schema(index.field_schema),
                    wait=True,
                )
            except Exception as exc:  # noqa: BLE001
                if not _is_existing_index_error(exc):
                    raise

    def delete_snapshot(self, snapshot_id: str) -> int:
        snapshot_filter = _snapshot_filter(snapshot_id)
        count_result = self._client.count(
            collection_name=self.collection_name,
            count_filter=snapshot_filter,
            exact=True,
        )
        deleted_points = int(getattr(count_result, "count", 0) or 0)
        if deleted_points == 0:
            return 0

        self._client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=snapshot_filter),
            wait=True,
        )
        return deleted_points

    def search_snapshot_chunks(
        self,
        *,
        snapshot_id: str,
        query_vector: list[float],
        limit: int,
        filters: CodeChunkSearchFilters | None = None,
        score_threshold: float | None = None,
    ) -> tuple[CodeChunkSearchHit, ...]:
        if limit <= 0:
            raise ValueError("limit must be positive.")
        if len(query_vector) != self.vector_size:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.vector_size}, got {len(query_vector)}."
            )

        try:
            query_response = self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                using=CODE_CHUNKS_VECTOR_NAME,
                query_filter=_search_filter(snapshot_id, filters or CodeChunkSearchFilters()),
                limit=limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=score_threshold,
            )
        except Exception as exc:  # noqa: BLE001
            raise RetrievalIndexError(f"Qdrant code chunk search failed: {exc}") from exc

        points = getattr(query_response, "points", None)
        if points is None and isinstance(query_response, tuple):
            points = query_response[0]
        if points is None:
            points = []

        hits: list[CodeChunkSearchHit] = []
        for point in points:
            payload = getattr(point, "payload", None) or {}
            if not isinstance(payload, dict):
                payload = dict(payload)
            hits.append(
                CodeChunkSearchHit(
                    point_id=str(getattr(point, "id", "")),
                    score=float(getattr(point, "score", 0.0) or 0.0),
                    payload=payload,
                )
            )
        return tuple(hits)


def _snapshot_filter(snapshot_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="snapshot_id",
                match=models.MatchValue(value=snapshot_id),
            )
        ]
    )


def _search_filter(snapshot_id: str, filters: CodeChunkSearchFilters) -> models.Filter:
    must: list[models.FieldCondition] = [
        models.FieldCondition(
            key="snapshot_id",
            match=models.MatchValue(value=snapshot_id),
        )
    ]

    _append_match_any(must, "workspace_unit_id", filters.workspace_unit_ids)
    _append_match_any(must, "language", filters.languages)
    _append_match_any(must, "source_scope", filters.source_scopes)
    _append_match_any(must, "chunk_kind", filters.chunk_kinds)
    _append_match_any(must, "package_id", filters.package_ids)
    _append_match_any(must, "file_path", filters.file_paths)
    if not filters.include_tests:
        must.append(models.FieldCondition(key="is_test", match=models.MatchValue(value=False)))

    return models.Filter(must=must)


def _append_match_any(
    conditions: list[models.FieldCondition],
    key: str,
    values: tuple[str, ...],
) -> None:
    if not values:
        return
    if len(values) == 1:
        conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=values[0])))
        return
    conditions.append(models.FieldCondition(key=key, match=models.MatchAny(any=list(values))))


def _distance() -> models.Distance:
    if CODE_CHUNKS_DISTANCE == "cosine":
        return models.Distance.COSINE
    if CODE_CHUNKS_DISTANCE == "dot":
        return models.Distance.DOT
    if CODE_CHUNKS_DISTANCE == "euclid":
        return models.Distance.EUCLID
    raise ValueError(f"Unsupported Qdrant distance: {CODE_CHUNKS_DISTANCE}")


def _payload_schema(field_schema: str) -> models.PayloadSchemaType:
    mapping = {
        "keyword": models.PayloadSchemaType.KEYWORD,
        "integer": models.PayloadSchemaType.INTEGER,
        "bool": models.PayloadSchemaType.BOOL,
        "text": models.PayloadSchemaType.TEXT,
    }
    try:
        return mapping[field_schema]
    except KeyError as exc:
        raise ValueError(f"Unsupported Qdrant payload field schema: {field_schema}") from exc


def _is_existing_index_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", status_code)
    message = str(exc).lower()
    return status_code in {400, 409} and ("already" in message or "exist" in message)


def _batches(
    items: tuple[tuple[CodeChunk, list[float]], ...],
    batch_size: int,
) -> Iterable[tuple[tuple[CodeChunk, list[float]], ...]]:
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]
