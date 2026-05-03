from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


class RepositoryServiceClientError(RuntimeError):
    def __init__(self, message: str, operation: str, status_code: int | None = None):
        super().__init__(message)
        self.operation = operation
        self.status_code = status_code


@dataclass(frozen=True)
class RepositoryServiceClient:
    base_url: str
    timeout_s: float = 10.0

    def get_previous_snapshot(
        self,
        repository_id: str,
        *,
        branch_name: str,
        head_commit_sha: str,
    ) -> dict[str, Any] | None:
        url = f"{self.base_url.rstrip('/')}/internal/v1/repositories/{repository_id}/snapshots/previous"
        params = {
            "branch_name": branch_name,
            "head_commit_sha": head_commit_sha,
        }
        try:
            response = httpx.get(url, params=params, timeout=self.timeout_s)
            if response.status_code == 204:
                return None

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(exc.response)
            raise RepositoryServiceClientError(
                f"RepositoryService previous snapshot lookup failed: {detail}",
                operation="previous_snapshot_lookup",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise RepositoryServiceClientError(
                f"RepositoryService previous snapshot lookup failed: {exc}",
                operation="previous_snapshot_lookup",
            ) from exc

    def upsert_snapshot(self, repository_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "branch_name": metadata["branch_name"],
            "commit_sha": metadata["commit_sha"],
            "tree_hash": metadata["tree_hash"],
            "commit_subject": metadata.get("commit_subject"),
            "commit_message": metadata.get("commit_message"),
            "commit_author_name": metadata.get("commit_author_name"),
            "commit_author_email": metadata.get("commit_author_email"),
            "commit_authored_at": _json_datetime(metadata.get("commit_authored_at")),
            "commit_committed_at": _json_datetime(metadata.get("commit_committed_at")),
            "files_total": metadata["files_total"],
            "go_files_total": metadata["go_files_total"],
            "readme_files_total": metadata["readme_files_total"],
            "bytes_total": metadata["bytes_total"],
            "set_active": True,
        }

        url = f"{self.base_url.rstrip('/')}/internal/v1/repositories/{repository_id}/snapshots"
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout_s)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(exc.response)
            raise RepositoryServiceClientError(
                f"RepositoryService snapshot upsert failed: {detail}",
                operation="snapshot_upsert",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise RepositoryServiceClientError(
                f"RepositoryService snapshot upsert failed: {exc}",
                operation="snapshot_upsert",
            ) from exc

    def upsert_analysis_artifact(
        self,
        repository_id: str,
        snapshot_id: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "produced_by_index_run_id": artifact["produced_by_index_run_id"],
            "artifact_kind": artifact["artifact_kind"],
            "storage_bucket": artifact["storage_bucket"],
            "storage_key": artifact["storage_key"],
            "content_type": artifact["content_type"],
            "format": artifact["format"],
            "checksum_sha256": artifact["checksum_sha256"],
            "size_bytes": artifact["size_bytes"],
            "row_count": artifact.get("row_count"),
            "schema_version": artifact["schema_version"],
        }

        url = (
            f"{self.base_url.rstrip('/')}/internal/v1/repositories/{repository_id}"
            f"/snapshots/{snapshot_id}/analysis-artifacts"
        )
        try:
            response = httpx.post(url, json=payload, timeout=self.timeout_s)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(exc.response)
            raise RepositoryServiceClientError(
                f"RepositoryService analysis artifact upsert failed: {detail}",
                operation="analysis_artifact_upsert",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise RepositoryServiceClientError(
                f"RepositoryService analysis artifact upsert failed: {exc}",
                operation="analysis_artifact_upsert",
            ) from exc


def _json_datetime(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def _response_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = response.text

    return f"status={response.status_code} body={body}"
