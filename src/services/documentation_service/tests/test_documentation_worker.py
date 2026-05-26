import pytest

pytest.importorskip("psycopg")

from app.infra.llm_client import LlmProviderError  # noqa: E402
from app.worker.documentation_worker import DocumentationWorker, WorkerSettings  # noqa: E402
from app.worker.job_store import ClaimedDocumentationRun  # noqa: E402


def test_worker_plans_sections_and_transitions_claimed_run_to_success() -> None:
    store = FakeStore()
    pipeline = FakePlanningPipeline()
    worker = DocumentationWorker(
        store=store,  # type: ignore[arg-type]
        planning_pipeline=pipeline,  # type: ignore[arg-type]
        worker_settings=WorkerSettings(
            worker_id="worker-a",
            poll_interval_s=0,
            heartbeat_seconds=60,
        ),
    )

    assert worker.run_once() is True

    assert store.progress_updates == [
        ("loading_project_model", 20),
        ("planning_sections", 35),
        ("retrieving_evidence", 65),
        ("generating_sections", 78),
        ("publishing_artifacts", 92),
        ("finalizing", 95),
    ]
    assert pipeline.planned_run_id == "run-1"
    assert store.effective_template_kind == "developer_handbook"
    assert store.succeeded_summary is not None
    assert store.succeeded_summary["scaffold_only"] is False
    assert store.succeeded_summary["sections_total"] == 1


def test_worker_requeues_retryable_llm_error_when_attempts_remain() -> None:
    store = FakeStore(max_attempts=3)
    pipeline = FailingPlanningPipeline(
        LlmProviderError(
            "rate limited",
            error_code="llm_provider_rate_limited",
            retryable=True,
        )
    )
    worker = DocumentationWorker(
        store=store,  # type: ignore[arg-type]
        planning_pipeline=pipeline,  # type: ignore[arg-type]
        worker_settings=WorkerSettings(
            worker_id="worker-a",
            poll_interval_s=0,
            heartbeat_seconds=60,
        ),
    )

    assert worker.run_once() is True

    assert store.failed_call == {
        "error_code": "llm_provider_rate_limited",
        "retryable": True,
    }


class FakePlanningPipeline:
    def __init__(self):
        self.planned_run_id = None

    def build_developer_handbook(
        self,
        run: ClaimedDocumentationRun,
        *,
        report_progress,
        report_template_selection=None,
    ):
        self.planned_run_id = run.id
        if report_template_selection is not None:
            report_template_selection("developer_handbook")
        report_progress("loading_project_model", 20)
        report_progress("planning_sections", 35)
        report_progress("retrieving_evidence", 65)
        report_progress("generating_sections", 78)
        report_progress("publishing_artifacts", 92)
        return FakePlanResult()


class FailingPlanningPipeline:
    def __init__(self, error: Exception):
        self._error = error

    def build_developer_handbook(
        self,
        run: ClaimedDocumentationRun,
        *,
        report_progress,
        report_template_selection=None,
    ):
        raise self._error


class FakePlanResult:
    sections = [object()]
    summary = {
        "scaffold_only": False,
        "sections_total": 1,
    }


class FakeStore:
    def __init__(self, *, max_attempts: int = 3):
        self._claimed = False
        self._max_attempts = max_attempts
        self.progress_updates: list[tuple[str, int]] = []
        self.effective_template_kind = None
        self.succeeded_summary = None
        self.failed_call = None

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
            max_attempts=self._max_attempts,
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

    def update_effective_template_kind(
        self,
        run_id: str,
        worker_id: str,
        effective_template_kind: str,
    ) -> None:
        self.effective_template_kind = effective_template_kind

    def mark_failed(
        self,
        run_id: str,
        worker_id: str,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = False,
    ) -> bool:
        self.failed_call = {
            "error_code": error_code,
            "retryable": retryable,
        }
        return True
