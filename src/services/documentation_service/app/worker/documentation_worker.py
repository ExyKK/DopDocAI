import logging
import os
import signal
import socket
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.worker.job_store import ClaimedDocumentationRun, DocumentationRunStore, LeaseLostError

logger = logging.getLogger("documentation_worker")


@dataclass(frozen=True)
class WorkerSettings:
    worker_id: str
    poll_interval_s: float
    heartbeat_seconds: int


class HeartbeatLoop:
    def __init__(
        self,
        store: DocumentationRunStore,
        run_id: str,
        worker_id: str,
        interval_s: int,
    ):
        self._store = store
        self._run_id = run_id
        self._worker_id = worker_id
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._lost: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{run_id}", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        self._thread.join(timeout=max(1, self._interval_s))

    def ensure_alive(self) -> None:
        if self._lost is not None:
            raise self._lost

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            try:
                self._store.heartbeat(self._run_id, self._worker_id)
            except BaseException as exc:
                self._lost = exc
                self._stop.set()
                logger.warning("Heartbeat failed for documentation_run=%s: %s", self._run_id, exc)


class DocumentationWorker:
    def __init__(
        self,
        store: DocumentationRunStore,
        planning_pipeline: Any,
        worker_settings: WorkerSettings,
    ):
        self._store = store
        self._planning_pipeline = planning_pipeline
        self._settings = worker_settings

    def run_once(self) -> bool:
        run = self._store.claim_next(self._settings.worker_id)
        if run is None:
            return False

        logger.info(
            "Claimed documentation_run=%s repository_id=%s snapshot_id=%s template=%s attempt=%s/%s",
            run.id,
            run.repository_id,
            run.snapshot_id,
            run.template_kind,
            run.attempt,
            run.max_attempts,
        )
        self._handle_run(run)
        return True

    def run_forever(self, stop_requested: Callable[[], bool]) -> None:
        while not stop_requested():
            claimed = self.run_once()
            if not claimed:
                time.sleep(self._settings.poll_interval_s)

    def _handle_run(self, run: ClaimedDocumentationRun) -> None:
        try:
            with HeartbeatLoop(
                self._store,
                run.id,
                self._settings.worker_id,
                self._settings.heartbeat_seconds,
            ) as heartbeat:
                def report_progress(
                    stage: str,
                    progress_pct: int,
                    *,
                    progress_current: int = 0,
                    progress_total: int = 0,
                ) -> None:
                    self._store.update_progress(
                        run.id,
                        self._settings.worker_id,
                        stage,
                        progress_pct,
                        progress_current=progress_current,
                        progress_total=progress_total,
                    )
                    heartbeat.ensure_alive()

                plan = self._planning_pipeline.build_developer_handbook(
                    run,
                    report_progress=report_progress,
                )
                heartbeat.ensure_alive()

                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "finalizing",
                    95,
                    progress_current=len(plan.sections),
                    progress_total=len(plan.sections),
                )
                heartbeat.ensure_alive()

                self._store.mark_succeeded(
                    run.id,
                    self._settings.worker_id,
                    verification_summary=plan.summary,
                )
                logger.info("Completed developer handbook run=%s", run.id)

        except Exception as exc:
            error_code = _map_error_code(exc)
            logger.exception(
                "Documentation run failed: documentation_run=%s error_code=%s",
                run.id,
                error_code,
            )
            updated = self._store.mark_failed(
                run.id,
                self._settings.worker_id,
                error_code,
                str(exc),
            )
            if not updated:
                logger.warning(
                    "Could not mark failed; lease may have been lost for documentation_run=%s",
                    run.id,
                )


def main() -> None:
    from app.core.config import settings

    setup_logging()
    stop = threading.Event()

    def _request_stop(signum, frame):
        logger.info("Stop requested by signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    if settings.s3_validate_on_start:
        _object_storage().ensure_bucket_exists()

    worker_id = settings.worker_id or _default_worker_id()
    worker_settings = WorkerSettings(
        worker_id=worker_id,
        poll_interval_s=settings.worker_poll_interval_s,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
    )
    worker = DocumentationWorker(
        store=DocumentationRunStore(
            database_url=settings.database_url,
            schema=settings.repo_db_schema,
            lease_seconds=settings.worker_lease_seconds,
        ),
        planning_pipeline=_planning_pipeline(),
        worker_settings=worker_settings,
    )

    logger.info("Documentation worker started worker_id=%s", worker_id)
    worker.run_forever(stop.is_set)
    logger.info("Documentation worker stopped worker_id=%s", worker_id)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _object_storage():
    from app.core.config import settings
    from app.infra.object_storage import ObjectStorageClient

    return ObjectStorageClient(
        endpoint_url=str(settings.s3_endpoint),
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        max_attempts=settings.s3_upload_max_attempts,
        retry_delay_s=settings.s3_upload_retry_delay_s,
    )


def _planning_pipeline():
    from app.core.config import settings
    from app.infra.repository_service_client import RepositoryServiceClient
    from app.infra.retrieval_client import RetrievalClient
    from app.pipeline.documentation_pipeline import DocumentationGenerationPipeline

    retrieval = None
    if settings.retrieval_enabled:
        retrieval = RetrievalClient(
            base_url=settings.retrieval_service_url,
            timeout_s=settings.retrieval_request_timeout_s,
            top_k=settings.retrieval_top_k,
            include_tests=settings.retrieval_include_tests,
            score_threshold=settings.retrieval_score_threshold,
        )

    return DocumentationGenerationPipeline(
        repository_service=RepositoryServiceClient(
            base_url=settings.repos_service_url,
            timeout_s=settings.request_timeout_s,
        ),
        storage=_object_storage(),
        retrieval=retrieval,
    )


def _map_error_code(exc: Exception) -> str:
    if isinstance(exc, LeaseLostError):
        return "worker_lease_lost"

    if exc.__class__.__name__ == "ObjectStorageError":
        return "artifact_publish_failed"

    if exc.__class__.__name__ == "RepositoryServiceClientError":
        if getattr(exc, "status_code", None) == 404:
            return "repository_not_found"
        if getattr(exc, "status_code", None) == 409:
            return "snapshot_conflict"
        return "transient_infrastructure_failure"

    return "unknown_error"


if __name__ == "__main__":
    main()
