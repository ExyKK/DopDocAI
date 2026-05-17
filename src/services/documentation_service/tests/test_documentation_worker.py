import pytest

pytest.importorskip("psycopg")

from app.worker.documentation_worker import DocumentationWorker, WorkerSettings  # noqa: E402
from app.worker.job_store import ClaimedDocumentationRun  # noqa: E402


def test_worker_scaffold_transitions_claimed_run_to_success() -> None:
    store = FakeStore()
    worker = DocumentationWorker(
        store=store,  # type: ignore[arg-type]
        worker_settings=WorkerSettings(
            worker_id="worker-a",
            poll_interval_s=0,
            heartbeat_seconds=60,
        ),
    )

    assert worker.run_once() is True

    assert store.progress_updates == [
        ("loading_project_model", 20),
        ("planning_sections", 45),
        ("finalizing", 95),
    ]
    assert store.succeeded_summary is not None
    assert store.succeeded_summary["scaffold_only"] is True
    assert store.succeeded_summary["sections_total"] == 0


class FakeStore:
    def __init__(self):
        self._claimed = False
        self.progress_updates: list[tuple[str, int]] = []
        self.succeeded_summary = None

    def claim_next(self, worker_id: str):
        if self._claimed:
            return None

        self._claimed = True
        return ClaimedDocumentationRun(
            id="run-1",
            repository_id="repo-1",
            snapshot_id="snapshot-1",
            source_index_run_id="index-run-1",
            base_snapshot_id=None,
            template_kind="developer_handbook",
            attempt=1,
            max_attempts=3,
        )

    def heartbeat(self, run_id: str, worker_id: str) -> None:
        return None

    def update_progress(
        self,
        run_id: str,
        worker_id: str,
        stage: str,
        progress_pct: int,
        progress_current: int = 0,
        progress_total: int = 0,
    ) -> None:
        self.progress_updates.append((stage, progress_pct))

    def mark_succeeded(self, run_id: str, worker_id: str, *, verification_summary=None) -> None:
        self.succeeded_summary = verification_summary

    def mark_failed(self, run_id: str, worker_id: str, error_code: str, error_message: str) -> bool:
        raise AssertionError(f"Unexpected failure: {error_code} {error_message}")
