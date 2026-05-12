import pytest
from fastapi import HTTPException

from app.api.routes.retrieval import RetrievalSearchRequestDto, search_retrieval
from app.retrieval.embeddings import EmbeddingProviderError
from app.retrieval.hybrid import analyze_query
from app.retrieval.qdrant_store import (
    CodeChunkSearchFilters,
    CodeChunkSearchHit,
    QdrantCodeChunkStore,
)
from app.retrieval.search import RetrievalSearcher, RetrievalSearchRequest


def test_retrieval_searcher_embeds_query_and_maps_qdrant_hits() -> None:
    provider = FakeEmbeddingProvider()
    store = FakeSearchStore()
    searcher = RetrievalSearcher(embedding_provider=provider, store=store)

    result = searcher.search(
        RetrievalSearchRequest(
            snapshot_id="snapshot-1",
            query="where is postgres.Repository.Get in backend/repo.go?",
            top_k=3,
            filters=CodeChunkSearchFilters(languages=("go",), include_tests=False),
        )
    )

    assert provider.queries[0].startswith("where is postgres.Repository.Get")
    assert "Symbols:" in provider.queries[0]
    assert "Paths:" in provider.queries[0]
    assert store.calls == [
        {
            "snapshot_id": "snapshot-1",
            "query_vector": [0.1, 0.2, 0.3],
            "limit": 12,
            "filters": CodeChunkSearchFilters(languages=("go",), include_tests=False),
            "score_threshold": None,
        }
    ]
    assert result.embedding_provider == "fake"
    assert result.matches[0].chunk_id == "chunk-1"
    assert result.matches[0].source.file_path == "backend/repo.go"
    assert result.matches[0].source.package is not None
    assert result.matches[0].source.package.import_path == "example/backend"
    assert result.matches[0].entity.name == "postgres.Repository.Get"
    assert result.matches[0].dense_score == 0.91
    assert result.matches[0].score_breakdown.total_boost > 0
    assert result.hybrid_enabled is True
    assert result.candidate_count == 1


def test_retrieval_searcher_reranks_symbol_path_match_over_dense_score() -> None:
    searcher = RetrievalSearcher(
        embedding_provider=FakeEmbeddingProvider(),
        store=FakeSearchStore(
            hits=(
                _hit(
                    chunk_id="dense-only",
                    score=0.92,
                    file_path="backend/unrelated.go",
                    name="postgres.Other",
                    text="func Other() {}",
                ),
                _hit(
                    chunk_id="exact-symbol",
                    score=0.82,
                    file_path="backend/repo.go",
                    name="postgres.Repository.Get",
                    text="func Get(ctx context.Context) ([]Section, error)",
                ),
            )
        ),
    )

    result = searcher.search(
        RetrievalSearchRequest(
            snapshot_id="snapshot-1",
            query="postgres.Repository.Get in backend/repo.go",
            top_k=1,
            filters=CodeChunkSearchFilters(),
        )
    )

    assert [match.chunk_id for match in result.matches] == ["exact-symbol"]
    assert result.matches[0].dense_score == 0.82
    assert result.matches[0].score_breakdown.path > 0
    assert result.matches[0].score_breakdown.symbol > 0


def test_general_query_keeps_dense_order_without_scope_boost() -> None:
    searcher = RetrievalSearcher(
        embedding_provider=FakeEmbeddingProvider(),
        store=FakeSearchStore(
            hits=(
                _hit(
                    chunk_id="runtime-symbol",
                    score=0.80,
                    file_path="backend/repo.go",
                    name="postgres.Repository.Get",
                    text="func Get(ctx context.Context) ([]Section, error)",
                ),
                _hit(
                    chunk_id="higher-dense",
                    score=0.82,
                    file_path="docs/architecture.md",
                    name="architecture.md",
                    text="Repository sections are loaded by the backend service.",
                ),
            )
        ),
    )

    result = searcher.search(
        RetrievalSearchRequest(
            snapshot_id="snapshot-1",
            query="где загружаются секции в репозитории",
            top_k=1,
            filters=CodeChunkSearchFilters(),
        )
    )

    assert [match.chunk_id for match in result.matches] == ["higher-dense"]
    assert result.matches[0].score_breakdown.total_boost == 0.0
    assert result.matches[0].score_breakdown.scope == 0.0


def test_russian_query_keeps_explicit_code_hints() -> None:
    query = analyze_query("где находится postgres.Repository.Get в backend/repo.go")

    assert query.symbol_hints == ("postgres.repository.get",)
    assert query.path_hints == ("backend/repo.go", "repo.go")
    assert "Symbols: postgres.repository.get" in query.expanded
    assert "Paths: backend/repo.go repo.go" in query.expanded


def test_qdrant_store_search_builds_snapshot_and_optional_filters() -> None:
    client = FakeQdrantSearchClient()
    store = QdrantCodeChunkStore(
        url="http://qdrant:6333",
        api_key=None,
        collection_name="code_chunks_v1",
        vector_size=3,
        client=client,
    )

    hits = store.search_snapshot_chunks(
        snapshot_id="snapshot-1",
        query_vector=[0.1, 0.2, 0.3],
        limit=5,
        filters=CodeChunkSearchFilters(
            workspace_unit_ids=("backend:api",),
            languages=("go", "markdown"),
            source_scopes=("runtime",),
            include_tests=False,
        ),
        score_threshold=0.25,
    )

    assert len(hits) == 1
    assert hits[0].score == 0.91
    assert client.query["collection_name"] == "code_chunks_v1"
    assert client.query["using"] == "dense"
    assert client.query["limit"] == 5
    assert client.query["score_threshold"] == 0.25
    query_filter = client.query["query_filter"]
    conditions = {condition.key: condition for condition in query_filter.must}
    assert conditions["snapshot_id"].match.value == "snapshot-1"
    assert conditions["workspace_unit_id"].match.value == "backend:api"
    assert conditions["language"].match.any == ["go", "markdown"]
    assert conditions["source_scope"].match.value == "runtime"
    assert conditions["is_test"].match.value is False


def test_retrieval_search_route_returns_normalized_response() -> None:
    response = search_retrieval(
        RetrievalSearchRequestDto.model_validate(
            {
                "snapshot_id": "snapshot-1",
                "query": "where are sections loaded?",
                "top_k": 3,
                "filters": {"languages": ["go", "go", ""], "include_tests": False},
            }
        ),
        searcher=RetrievalSearcher(
            embedding_provider=FakeEmbeddingProvider(),
            store=FakeSearchStore(),
        ),
    )

    body = response.model_dump()
    assert body["snapshot_id"] == "snapshot-1"
    assert body["embedding_provider"] == "fake"
    assert body["hybrid"]["enabled"] is True
    assert body["hybrid"]["candidate_count"] == 1
    assert len(body["matches"]) == 1
    match = body["matches"][0]
    assert match["chunk_id"] == "chunk-1"
    assert match["dense_score"] == 0.91
    assert match["score_breakdown"]["total_boost"] == 0.0
    assert match["source"]["file_path"] == "backend/repo.go"
    assert match["entity"]["chunk_kind"] == "go_symbol"


def test_retrieval_search_route_maps_embedding_failures_to_bad_gateway() -> None:
    with pytest.raises(HTTPException) as exc:
        search_retrieval(
            RetrievalSearchRequestDto.model_validate(
                {
                    "snapshot_id": "snapshot-1",
                    "query": "anything",
                }
            ),
            searcher=RetrievalSearcher(
                embedding_provider=FailingEmbeddingProvider(),
                store=FakeSearchStore(),
            ),
        )

    assert exc.value.status_code == 502
    assert "Embedding provider failed" in exc.value.detail


def test_retrieval_search_route_deduplicates_filters() -> None:
    store = FakeSearchStore()
    searcher = RetrievalSearcher(
        embedding_provider=FakeEmbeddingProvider(),
        store=store,
    )

    search_retrieval(
        RetrievalSearchRequestDto.model_validate(
            {
                "snapshot_id": "snapshot-1",
                "query": "where are sections loaded?",
                "top_k": 3,
                "filters": {"languages": ["go", "go", ""], "include_tests": False},
            }
        ),
        searcher=searcher,
    )

    assert store.calls[0]["filters"] == CodeChunkSearchFilters(languages=("go",), include_tests=False)


class FakeEmbeddingProvider:
    provider = "fake"
    model = "fake-model"
    dimension = 3
    batch_size = 2

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_documents(self, texts):
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed_query(self, text: str) -> list[float]:
        raise EmbeddingProviderError("service unavailable")


class FakeSearchStore:
    def __init__(self, *, hits: tuple[CodeChunkSearchHit, ...] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._hits = hits

    def search_snapshot_chunks(
        self,
        *,
        snapshot_id: str,
        query_vector: list[float],
        limit: int,
        filters: CodeChunkSearchFilters | None = None,
        score_threshold: float | None = None,
    ) -> tuple[CodeChunkSearchHit, ...]:
        self.calls.append(
            {
                "snapshot_id": snapshot_id,
                "query_vector": query_vector,
                "limit": limit,
                "filters": filters,
                "score_threshold": score_threshold,
            }
        )
        return self._hits or (_hit(),)


def _hit(
    *,
    chunk_id: str = "chunk-1",
    score: float = 0.91,
    file_path: str = "backend/repo.go",
    name: str = "postgres.Repository.Get",
    text: str = "func Get(ctx context.Context) ([]Section, error)",
) -> CodeChunkSearchHit:
    return CodeChunkSearchHit(
        point_id=chunk_id,
        score=score,
        payload={
            "chunk_id": chunk_id,
            "snapshot_id": "snapshot-1",
            "repository_id": "repo-1",
            "commit_sha": "a" * 40,
            "file_path": file_path,
            "language": "go",
            "kind": "method",
            "chunk_kind": "go_symbol",
            "is_test": False,
            "source_scope": "runtime",
            "text": text,
            "workspace_unit_id": "backend:api",
            "package_id": "example/backend#postgres",
            "package": {
                "package_id": "example/backend#postgres",
                "name": "postgres",
                "import_path": "example/backend",
                "dir_path": "backend",
                "module_path": "example",
            },
            "name": name,
            "start_line": 20,
            "end_line": 50,
            "symbol_id": "symbol-1",
            "symbol_signature": "func Get(ctx context.Context) ([]Section, error)",
        },
    )


class FakeQdrantPoint:
    id = "point-1"
    score = 0.91
    payload = {"chunk_id": "chunk-1", "snapshot_id": "snapshot-1"}


class FakeQdrantQueryResponse:
    points = [FakeQdrantPoint()]


class FakeQdrantSearchClient:
    def __init__(self) -> None:
        self.query: dict[str, object] = {}

    def query_points(self, **kwargs) -> FakeQdrantQueryResponse:
        self.query = kwargs
        return FakeQdrantQueryResponse()
