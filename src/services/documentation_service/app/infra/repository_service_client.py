from dataclasses import dataclass
from typing import Any

import httpx


class RepositoryServiceClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AnalysisArtifactRef:
    id: str
    snapshot_id: str
    artifact_kind: str
    storage_bucket: str
    storage_key: str
    schema_version: int


@dataclass(frozen=True)
class DocumentationArtifactRef:
    id: str
    documentation_run_id: str
    section_id: str | None
    attempt: int
    artifact_kind: str
    storage_bucket: str
    storage_key: str
    content_type: str
    format: str
    checksum_sha256: str
    size_bytes: int
    schema_version: int


class RepositoryServiceClient:
    def __init__(self, base_url: str, timeout_s: float):
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def list_analysis_artifacts(
        self,
        repository_id: str,
        snapshot_id: str,
    ) -> list[AnalysisArtifactRef]:
        url = (
            f"{self._base_url}/internal/v1/repositories/{repository_id}"
            f"/snapshots/{snapshot_id}/analysis-artifacts"
        )
        response = httpx.get(url, timeout=self._timeout_s)
        if not response.is_success:
            raise RepositoryServiceClientError(
                f"RepositoryService analysis artifact list failed: status={response.status_code} body={_truncate(response.text, 512)}",
                status_code=response.status_code,
            )

        return [
            AnalysisArtifactRef(
                id=item["id"],
                snapshot_id=item["snapshot_id"],
                artifact_kind=item["artifact_kind"],
                storage_bucket=item["storage_bucket"],
                storage_key=item["storage_key"],
                schema_version=item["schema_version"],
            )
            for item in response.json()
        ]

    def replace_documentation_sections(
        self,
        documentation_run_id: str,
        sections: list[dict[str, Any]],
    ) -> None:
        url = (
            f"{self._base_url}/internal/v1/documentation-runs/{documentation_run_id}"
            "/sections/plan"
        )
        response = httpx.post(url, json={"sections": sections}, timeout=self._timeout_s)
        if not response.is_success:
            raise RepositoryServiceClientError(
                f"RepositoryService documentation section replacement failed: status={response.status_code} body={_truncate(response.text, 512)}",
                status_code=response.status_code,
            )

    def register_documentation_artifact(
        self,
        documentation_run_id: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._base_url}/internal/v1/documentation-runs/{documentation_run_id}/artifacts"
        response = httpx.post(url, json=artifact, timeout=self._timeout_s)
        if not response.is_success:
            raise RepositoryServiceClientError(
                f"RepositoryService documentation artifact registration failed: status={response.status_code} body={_truncate(response.text, 512)}",
                status_code=response.status_code,
            )

        return response.json()

    def list_documentation_artifacts(
        self,
        documentation_run_id: str,
        *,
        attempt: int | None = None,
    ) -> list[DocumentationArtifactRef]:
        url = f"{self._base_url}/internal/v1/documentation-runs/{documentation_run_id}/artifacts"
        params = {"attempt": attempt} if attempt is not None else None
        response = httpx.get(url, params=params, timeout=self._timeout_s)
        if not response.is_success:
            raise RepositoryServiceClientError(
                f"RepositoryService documentation artifact list failed: status={response.status_code} body={_truncate(response.text, 512)}",
                status_code=response.status_code,
            )

        return [
            DocumentationArtifactRef(
                id=item["id"],
                documentation_run_id=item["documentation_run_id"],
                section_id=item.get("section_id"),
                attempt=int(item.get("attempt") or 1),
                artifact_kind=item["artifact_kind"],
                storage_bucket=item["storage_bucket"],
                storage_key=item["storage_key"],
                content_type=item["content_type"],
                format=item["format"],
                checksum_sha256=item["checksum_sha256"],
                size_bytes=int(item["size_bytes"]),
                schema_version=int(item["schema_version"]),
            )
            for item in response.json()
        ]


def _truncate(value: str, max_length: int) -> str:
    if not value:
        return ""

    return value if len(value) <= max_length else value[:max_length]
