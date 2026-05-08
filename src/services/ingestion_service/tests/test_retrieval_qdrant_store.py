from dataclasses import dataclass

from app.retrieval.chunks import CodeChunk
from app.retrieval.qdrant_store import QdrantCodeChunkStore
from app.retrieval.storage_model import CODE_CHUNKS_VECTOR_NAME, payload_index_field_names
from app.retrieval.vectorizer import HashingVectorizer


def test_replace_snapshot_chunks_deletes_existing_points_and_batch_upserts() -> None:
    client = FakeQdrantClient(existing_count=2)
    store = QdrantCodeChunkStore(
        url="http://qdrant:6333",
        api_key=None,
        collection_name="code_chunks_v1",
        vector_size=8,
        batch_size=2,
        client=client,
    )
    chunks = tuple(
        CodeChunk(
            chunk_id=f"00000000-0000-0000-0000-00000000000{index}",
            text=f"func Symbol{index} returns a service",
            payload={
                "chunk_id": f"00000000-0000-0000-0000-00000000000{index}",
                "snapshot_id": "snapshot-id",
                "repository_id": "repo-id",
                "commit_sha": "a" * 40,
                "file_path": f"file{index}.go",
                "language": "go",
                "kind": "function",
                "chunk_kind": "go_symbol",
                "is_test": False,
                "source_scope": "runtime",
                "text": f"func Symbol{index} returns a service",
            },
        )
        for index in range(3)
    )

    result = store.replace_snapshot_chunks(
        snapshot_id="snapshot-id",
        chunks=chunks,
        vectorizer=HashingVectorizer(8),
    )

    assert result.deleted_points == 2
    assert result.upserted_points == 3
    assert result.batches_total == 2
    assert client.deleted is True
    assert [len(batch) for batch in client.upserts] == [2, 1]
    assert set(client.payload_indexes) == set(payload_index_field_names())
    first_point = client.upserts[0][0]
    assert first_point.vector.keys() == {CODE_CHUNKS_VECTOR_NAME}
    assert len(first_point.vector[CODE_CHUNKS_VECTOR_NAME]) == 8
    assert first_point.payload["snapshot_id"] == "snapshot-id"


def test_replace_snapshot_chunks_creates_collection_when_missing() -> None:
    client = FakeQdrantClient(collection_exists=False, existing_count=0)
    store = QdrantCodeChunkStore(
        url="http://qdrant:6333",
        api_key=None,
        collection_name="code_chunks_v1",
        vector_size=16,
        batch_size=10,
        client=client,
    )

    result = store.replace_snapshot_chunks(
        snapshot_id="snapshot-id",
        chunks=(),
        vectorizer=HashingVectorizer(16),
    )

    assert result.deleted_points == 0
    assert result.upserted_points == 0
    assert client.created_collection == "code_chunks_v1"
    assert client.upserts == []


@dataclass(frozen=True)
class FakeCountResult:
    count: int


class FakeQdrantClient:
    def __init__(self, *, collection_exists: bool = True, existing_count: int) -> None:
        self._collection_exists = collection_exists
        self._existing_count = existing_count
        self.created_collection: str | None = None
        self.payload_indexes: list[str] = []
        self.deleted = False
        self.upserts: list[list[object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        return self._collection_exists

    def create_collection(self, *, collection_name: str, vectors_config: object) -> None:
        self.created_collection = collection_name
        self._collection_exists = True

    def create_payload_index(
        self,
        *,
        collection_name: str,
        field_name: str,
        field_schema: object,
        wait: bool,
    ) -> None:
        self.payload_indexes.append(field_name)

    def count(self, *, collection_name: str, count_filter: object, exact: bool) -> FakeCountResult:
        return FakeCountResult(self._existing_count)

    def delete(self, *, collection_name: str, points_selector: object, wait: bool) -> None:
        self.deleted = True
        self._existing_count = 0

    def upsert(self, *, collection_name: str, points: list[object], wait: bool) -> None:
        self.upserts.append(points)
