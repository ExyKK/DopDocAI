from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Distance, VectorParams, ScoredPoint
from qdrant_client.http.exceptions import UnexpectedResponse
from typing import List, Dict, Any, Optional
import uuid


class QdrantManager:
    """Encapsulates Qdrant connection, collection creation and buffered upsert.

    Usage:
        mgr = QdrantManager(url, api_key, collection_name, batch_size=64)
        mgr.ensure_collection(vector_size)
        mgr.add_point_from_vector(file_hash, chunk_index, vector, metadata)
        mgr.flush()
    """

    def __init__(self, url: str, api_key: Optional[str], collection_name: str, batch_size: int = 64):
        self.client = QdrantClient(url=url, api_key=api_key)
        self.collection_name = collection_name
        self.batch_size = batch_size
        self._points_buffer: List[PointStruct] = []
        self._total_upserted = 0
        self._vector_size: Optional[int] = None

    def init_collection(self, vector_size: int, distance: Distance = Distance.COSINE):
        """Initializes Qdrant collection of points."""

        collections = self.client.get_collections().collections
        if any(col.name == self.collection_name for col in collections):
            print(f"Collection '{self.collection_name}' already exists.")
            return

        print(f"Creating Qdrant collection '{self.collection_name}' (vector_size={vector_size}) ...")
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
        )
        self._vector_size = vector_size
        print("Created collection.")

    def _make_point_id(self, file_hash: str, chunk_index: int) -> str:
        """Deterministic UUIDv5 based on file_hash and chunk index.
        Returns canonical UUID string which Qdrant accepts as a point id.
        """
        return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{file_hash}:{chunk_index}"))

    def add_point_from_vector(self, file_hash: str, chunk_index: int, vector: List[float], payload: Dict[str, Any]):
        """Create PointStruct and append to internal buffer. Flushes automatically when buffer >= batch_size."""

        pt_id = self._make_point_id(file_hash, chunk_index)
        point = PointStruct(id=pt_id, vector=list(map(float, vector)), payload=payload)
        self._points_buffer.append(point)
        if len(self._points_buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        """Upload buffered points to Qdrant and clear buffer."""

        if not self._points_buffer:
            return
        try:
            self.client.upsert(collection_name=self.collection_name, points=self._points_buffer)
            self._total_upserted += len(self._points_buffer)
            print(f"Upserted {len(self._points_buffer)} points (total {self._total_upserted})")
        except UnexpectedResponse as e:
            print("Qdrant upsert failed:", e)
            # attempt to show server detail
            try:
                print("Response content:", getattr(e, "response", None) or getattr(e, "http_response", None))
            except Exception:
                pass
            raise
        finally:
            self._points_buffer = []

    @property
    def total_upserted(self) -> int:
        return self._total_upserted

    def search(self, query_vector: list[float], limit: int = 8) -> list:
        res = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,  # важно: query, не query_vector
            limit=limit,
            with_payload=True,
        )
        # В 1.16.x обычно возвращается объект, у которого .points
        return list(res.points)