from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


class RepositoryServiceClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class RepositoryServiceClient:
    base_url: str
    timeout_s: float = 10.0

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
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            raise RepositoryServiceClientError(
                f"RepositoryService snapshot upsert failed: {exc}"
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
