from dataclasses import dataclass
from typing import Any

import httpx


class RetrievalClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: str
    score: float
    text: str
    file_path: str | None
    language: str | None
    source_scope: str | None
    start_line: int | None
    end_line: int | None
    symbol_name: str | None
    source_kind: str


class RetrievalClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float,
        top_k: int,
        include_tests: bool,
        score_threshold: float | None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._top_k = top_k
        self._include_tests = include_tests
        self._score_threshold = score_threshold

    def search(self, snapshot_id: str, query: str) -> list[RetrievedSource]:
        request = {
            "snapshot_id": snapshot_id,
            "query": query,
            "top_k": self._top_k,
            "filters": {
                "workspace_unit_ids": [],
                "languages": [],
                "source_scopes": [],
                "chunk_kinds": [],
                "package_ids": [],
                "file_paths": [],
                "include_tests": self._include_tests,
            },
            "score_threshold": self._score_threshold,
        }
        response = httpx.post(
            f"{self._base_url}/internal/v1/retrieval/search",
            json=request,
            timeout=self._timeout_s,
        )
        if not response.is_success:
            raise RetrievalClientError(
                f"Retrieval search failed: status={response.status_code} body={_truncate(response.text, 512)}"
            )

        return [_to_source(match) for match in response.json().get("matches", [])]


def _to_source(match: dict[str, Any]) -> RetrievedSource:
    source = match.get("source") or {}
    entity = match.get("entity") or {}
    return RetrievedSource(
        chunk_id=match.get("chunk_id") or "",
        score=float(match.get("score") or 0.0),
        text=match.get("text") or "",
        file_path=source.get("file_path"),
        language=source.get("language"),
        source_scope=source.get("source_scope"),
        start_line=source.get("start_line"),
        end_line=source.get("end_line"),
        symbol_name=entity.get("name"),
        source_kind=entity.get("kind") or entity.get("chunk_kind") or "retrieval_chunk",
    )


def _truncate(value: str, max_length: int) -> str:
    if not value:
        return ""

    return value if len(value) <= max_length else value[:max_length]
