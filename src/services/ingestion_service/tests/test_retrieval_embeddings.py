import httpx
import pytest

from app.retrieval.embeddings import (
    EmbeddingProviderError,
    HashEmbeddingProvider,
    HttpEmbeddingProvider,
)


def test_hash_embedding_provider_supports_documents_and_query_prefixes() -> None:
    provider = HashEmbeddingProvider(
        dimension=8,
        batch_size=2,
        document_prefix="doc:",
        query_prefix="query:",
    )

    batch = provider.embed_documents(["Find command flags", "Execute command"])
    query_vector = provider.embed_query("Find command flags")

    assert batch.provider == "hash"
    assert batch.model == "hashing-vectorizer"
    assert batch.dimension == 8
    assert batch.inputs_total == 2
    assert batch.batches_total == 1
    assert len(batch.vectors) == 2
    assert all(len(vector) == 8 for vector in batch.vectors)
    assert len(query_vector) == 8
    assert query_vector != batch.vectors[0]


def test_http_embedding_provider_batches_requests_and_validates_dimensions() -> None:
    client = FakeEmbeddingClient(dimension=4)
    provider = HttpEmbeddingProvider(
        base_url="http://embedding_service:19400",
        model="jinaai/jina-code-embeddings-0.5b",
        dimension=4,
        batch_size=2,
        timeout_s=10,
        max_attempts=1,
        retry_delay_s=0,
        document_prefix="doc:",
        query_prefix="query:",
        client=client,
    )

    batch = provider.embed_documents(["one", "two", "three"])
    query_vector = provider.embed_query("where is cobra command")

    assert batch.provider == "jina_http"
    assert batch.model == "jinaai/jina-code-embeddings-0.5b"
    assert batch.dimension == 4
    assert batch.inputs_total == 3
    assert batch.batches_total == 2
    assert len(batch.vectors) == 3
    assert len(query_vector) == 4
    assert [request["input_type"] for request in client.requests] == ["document", "document", "query"]
    assert client.requests[0]["texts"] == ["doc:one", "doc:two"]
    assert client.requests[-1]["texts"] == ["query:where is cobra command"]


def test_http_embedding_provider_retries_transient_failures() -> None:
    client = FakeEmbeddingClient(dimension=4, failures_before_success=1)
    provider = HttpEmbeddingProvider(
        base_url="http://embedding_service:19400",
        model="jinaai/jina-code-embeddings-0.5b",
        dimension=4,
        batch_size=2,
        timeout_s=10,
        max_attempts=2,
        retry_delay_s=0,
        document_prefix="doc:",
        query_prefix="query:",
        client=client,
    )

    batch = provider.embed_documents(["one"])

    assert batch.inputs_total == 1
    assert client.calls == 2


def test_http_embedding_provider_rejects_wrong_dimensions() -> None:
    client = FakeEmbeddingClient(dimension=3)
    provider = HttpEmbeddingProvider(
        base_url="http://embedding_service:19400",
        model="jinaai/jina-code-embeddings-0.5b",
        dimension=4,
        batch_size=2,
        timeout_s=10,
        max_attempts=1,
        retry_delay_s=0,
        document_prefix="doc:",
        query_prefix="query:",
        client=client,
    )

    with pytest.raises(EmbeddingProviderError, match="dimension mismatch"):
        provider.embed_documents(["one"])


class FakeEmbeddingClient:
    def __init__(self, *, dimension: int, failures_before_success: int = 0) -> None:
        self.dimension = dimension
        self.failures_before_success = failures_before_success
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    def post(self, path: str, *, json: dict[str, object]) -> httpx.Response:
        self.calls += 1
        request = httpx.Request("POST", f"http://embedding_service:19400{path}")
        if self.calls <= self.failures_before_success:
            return httpx.Response(503, json={"detail": "warming up"}, request=request)

        texts = list(json["texts"])
        self.requests.append(
            {
                "path": path,
                "input_type": json["input_type"],
                "texts": texts,
            }
        )
        return httpx.Response(
            200,
            request=request,
            json={
                "model": "jinaai/jina-code-embeddings-0.5b",
                "dimension": self.dimension,
                "input_type": json["input_type"],
                "embeddings": [[float(index + 1)] * self.dimension for index, _ in enumerate(texts)],
            },
        )
