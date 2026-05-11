import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx

from app.retrieval.vectorizer import HashingVectorizer

EmbeddingInputType = Literal["document", "query"]


class EmbeddingProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[list[float], ...]
    provider: str
    model: str
    dimension: int
    batches_total: int
    inputs_total: int


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimension: int
    batch_size: int

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        pass

    def embed_query(self, text: str) -> list[float]:
        pass


class HashEmbeddingProvider:
    provider = "hash"
    model = "hashing-vectorizer"

    def __init__(
        self,
        *,
        dimension: int,
        batch_size: int,
        document_prefix: str,
        query_prefix: str,
    ) -> None:
        self.dimension = dimension
        self.batch_size = batch_size
        self._document_prefix = document_prefix
        self._query_prefix = query_prefix
        self._vectorizer = HashingVectorizer(dimension)

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors = tuple(self._vectorizer.vectorize(f"{self._document_prefix}{text}") for text in texts)
        return EmbeddingBatch(
            vectors=vectors,
            provider=self.provider,
            model=self.model,
            dimension=self.dimension,
            batches_total=_batch_count(len(texts), self.batch_size),
            inputs_total=len(texts),
        )

    def embed_query(self, text: str) -> list[float]:
        return self._vectorizer.vectorize(f"{self._query_prefix}{text}")


class HttpEmbeddingProvider:
    provider = "jina_http"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimension: int,
        batch_size: int,
        timeout_s: float,
        max_attempts: int,
        retry_delay_s: float,
        document_prefix: str,
        query_prefix: str,
        client: Any | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")

        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self._max_attempts = max_attempts
        self._retry_delay_s = retry_delay_s
        self._document_prefix = document_prefix
        self._query_prefix = query_prefix
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s)

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        batches_total = 0
        for batch in _batches([f"{self._document_prefix}{text}" for text in texts], self.batch_size):
            vectors.extend(self._embed_batch(batch, input_type="document"))
            batches_total += 1

        return EmbeddingBatch(
            vectors=tuple(vectors),
            provider=self.provider,
            model=self.model,
            dimension=self.dimension,
            batches_total=batches_total,
            inputs_total=len(texts),
        )

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed_batch([f"{self._query_prefix}{text}"], input_type="query")
        return vectors[0]

    def _embed_batch(self, texts: list[str], *, input_type: EmbeddingInputType) -> list[list[float]]:
        if not texts:
            return []

        response_json = self._post_with_retry(
            "/internal/embeddings",
            json={
                "texts": texts,
                "input_type": input_type,
                "model": self.model,
                "normalize": True,
            },
        )
        vectors = response_json.get("embeddings")
        if not isinstance(vectors, list):
            raise EmbeddingProviderError("Embedding service returned no embeddings.")
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(
                f"Embedding service returned {len(vectors)} embeddings for {len(texts)} inputs."
            )

        parsed_vectors: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimension:
                raise EmbeddingProviderError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector) if isinstance(vector, list) else 'invalid'}."
                )
            parsed_vectors.append([float(value) for value in vector])
        return parsed_vectors

    def _post_with_retry(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.post(path, json=json)
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                time.sleep(self._retry_delay_s)

        raise EmbeddingProviderError(f"Embedding provider request failed: {last_error}") from last_error


def _batch_count(items_total: int, batch_size: int) -> int:
    if items_total == 0:
        return 0
    return (items_total + batch_size - 1) // batch_size


def _batches(items: list[str], batch_size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]
