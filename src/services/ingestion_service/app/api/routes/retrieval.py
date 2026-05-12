from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_retrieval_searcher
from app.retrieval.embeddings import EmbeddingProviderError
from app.retrieval.qdrant_store import CodeChunkSearchFilters, RetrievalIndexError
from app.retrieval.search import (
    RetrievalEntity,
    RetrievalMatch,
    RetrievalPackage,
    RetrievalScoreBreakdown,
    RetrievalSearcher,
    RetrievalSearchError,
    RetrievalSearchRequest,
    RetrievalSearchResult,
    RetrievalSource,
)

router = APIRouter(prefix="/internal/v1/retrieval", tags=["internal-retrieval"])


class RetrievalFilterRequest(BaseModel):
    workspace_unit_ids: list[str] = Field(default_factory=list, max_length=64)
    languages: list[str] = Field(default_factory=list, max_length=32)
    source_scopes: list[str] = Field(default_factory=list, max_length=32)
    chunk_kinds: list[str] = Field(default_factory=list, max_length=32)
    package_ids: list[str] = Field(default_factory=list, max_length=64)
    file_paths: list[str] = Field(default_factory=list, max_length=128)
    include_tests: bool = True


class RetrievalSearchRequestDto(BaseModel):
    snapshot_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=8000)
    top_k: int = Field(default=8, ge=1, le=50)
    filters: RetrievalFilterRequest = Field(default_factory=RetrievalFilterRequest)
    score_threshold: float | None = Field(default=None, ge=0.0)


class RetrievalPackageDto(BaseModel):
    package_id: str | None = None
    name: str | None = None
    import_path: str | None = None
    dir_path: str | None = None
    module_path: str | None = None


class RetrievalSourceDto(BaseModel):
    repository_id: str
    snapshot_id: str
    commit_sha: str
    file_path: str
    language: str
    source_scope: str
    is_test: bool
    start_line: int | None = None
    end_line: int | None = None
    workspace_unit_id: str | None = None
    package: RetrievalPackageDto | None = None


class RetrievalEntityDto(BaseModel):
    kind: str
    chunk_kind: str
    name: str | None = None
    symbol_id: str | None = None
    symbol_signature: str | None = None


class RetrievalScoreBreakdownDto(BaseModel):
    dense: float
    path: float
    symbol: float
    lexical: float
    scope: float
    total_boost: float


class RetrievalMatchDto(BaseModel):
    chunk_id: str
    score: float
    dense_score: float
    score_breakdown: RetrievalScoreBreakdownDto
    text: str
    source: RetrievalSourceDto
    entity: RetrievalEntityDto


class RetrievalHybridDto(BaseModel):
    enabled: bool
    candidate_count: int
    query_terms: list[str]
    path_hints: list[str]
    symbol_hints: list[str]


class RetrievalSearchResponseDto(BaseModel):
    snapshot_id: str
    query: str
    top_k: int
    elapsed_ms: float
    embedding_provider: str
    embedding_model: str
    hybrid: RetrievalHybridDto
    matches: list[RetrievalMatchDto]


@router.post("/search", response_model=RetrievalSearchResponseDto)
def search_retrieval(
    request: RetrievalSearchRequestDto,
    searcher: Annotated[RetrievalSearcher, Depends(get_retrieval_searcher)],
) -> RetrievalSearchResponseDto:
    try:
        result = searcher.search(
            RetrievalSearchRequest(
                snapshot_id=request.snapshot_id,
                query=request.query,
                top_k=request.top_k,
                filters=_filters_from_request(request.filters),
                score_threshold=request.score_threshold,
            )
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding provider failed: {exc}",
        ) from exc
    except RetrievalIndexError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Retrieval store failed: {exc}",
        ) from exc
    except RetrievalSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return _response_from_result(result)


def _filters_from_request(filters: RetrievalFilterRequest) -> CodeChunkSearchFilters:
    return CodeChunkSearchFilters(
        workspace_unit_ids=_unique_tuple(filters.workspace_unit_ids),
        languages=_unique_tuple(filters.languages),
        source_scopes=_unique_tuple(filters.source_scopes),
        chunk_kinds=_unique_tuple(filters.chunk_kinds),
        package_ids=_unique_tuple(filters.package_ids),
        file_paths=_unique_tuple(filters.file_paths),
        include_tests=filters.include_tests,
    )


def _response_from_result(result: RetrievalSearchResult) -> RetrievalSearchResponseDto:
    return RetrievalSearchResponseDto(
        snapshot_id=result.snapshot_id,
        query=result.query,
        top_k=result.top_k,
        elapsed_ms=result.elapsed_ms,
        embedding_provider=result.embedding_provider,
        embedding_model=result.embedding_model,
        hybrid=RetrievalHybridDto(
            enabled=result.hybrid_enabled,
            candidate_count=result.candidate_count,
            query_terms=list(result.query_terms),
            path_hints=list(result.path_hints),
            symbol_hints=list(result.symbol_hints),
        ),
        matches=[_match_dto(match) for match in result.matches],
    )


def _match_dto(match: RetrievalMatch) -> RetrievalMatchDto:
    return RetrievalMatchDto(
        chunk_id=match.chunk_id,
        score=match.score,
        dense_score=match.dense_score,
        score_breakdown=_score_breakdown_dto(match.score_breakdown),
        text=match.text,
        source=_source_dto(match.source),
        entity=_entity_dto(match.entity),
    )


def _score_breakdown_dto(score_breakdown: RetrievalScoreBreakdown) -> RetrievalScoreBreakdownDto:
    return RetrievalScoreBreakdownDto(
        dense=score_breakdown.dense,
        path=score_breakdown.path,
        symbol=score_breakdown.symbol,
        lexical=score_breakdown.lexical,
        scope=score_breakdown.scope,
        total_boost=score_breakdown.total_boost,
    )


def _source_dto(source: RetrievalSource) -> RetrievalSourceDto:
    return RetrievalSourceDto(
        repository_id=source.repository_id,
        snapshot_id=source.snapshot_id,
        commit_sha=source.commit_sha,
        file_path=source.file_path,
        language=source.language,
        source_scope=source.source_scope,
        is_test=source.is_test,
        start_line=source.start_line,
        end_line=source.end_line,
        workspace_unit_id=source.workspace_unit_id,
        package=_package_dto(source.package),
    )


def _package_dto(package: RetrievalPackage | None) -> RetrievalPackageDto | None:
    if package is None:
        return None
    return RetrievalPackageDto(
        package_id=package.package_id,
        name=package.name,
        import_path=package.import_path,
        dir_path=package.dir_path,
        module_path=package.module_path,
    )


def _entity_dto(entity: RetrievalEntity) -> RetrievalEntityDto:
    return RetrievalEntityDto(
        kind=entity.kind,
        chunk_kind=entity.chunk_kind,
        name=entity.name,
        symbol_id=entity.symbol_id,
        symbol_signature=entity.symbol_signature,
    )


def _unique_tuple(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)
