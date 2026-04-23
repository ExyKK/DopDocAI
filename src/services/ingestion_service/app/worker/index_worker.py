import logging
import os
import signal
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from app.core.config import settings
from app.infra.git_client import GitClient, RepoCloneError
from app.infra.repository_service_client import (
    RepositoryServiceClient,
    RepositoryServiceClientError,
)
from app.worker.job_store import ClaimedIndexRun, IndexRunStore, LeaseLostError
from app.worker.snapshot_resolver import SnapshotResolver

logger = logging.getLogger("ingestion_worker")


@dataclass(frozen=True)
class WorkerSettings:
    worker_id: str
    poll_interval_s: float
    heartbeat_seconds: int


class HeartbeatLoop:
    def __init__(
        self,
        store: IndexRunStore,
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
                logger.warning("Heartbeat failed for index_run=%s: %s", self._run_id, exc)


class IndexWorker:
    def __init__(
        self,
        store: IndexRunStore,
        snapshots: RepositoryServiceClient,
        resolver: SnapshotResolver,
        worker_settings: WorkerSettings,
    ):
        self._store = store
        self._snapshots = snapshots
        self._resolver = resolver
        self._settings = worker_settings

    def run_once(self) -> bool:
        run = self._store.claim_next(self._settings.worker_id)
        if run is None:
            return False

        logger.info(
            "Claimed index_run=%s repository_id=%s attempt=%s/%s",
            run.id,
            run.repository_id,
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

    def _handle_run(self, run: ClaimedIndexRun) -> None:
        resolved = None
        try:
            with HeartbeatLoop(
                self._store,
                run.id,
                self._settings.worker_id,
                self._settings.heartbeat_seconds,
            ) as heartbeat:
                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "cloning",
                    20,
                    "Cloning repository.",
                    payload={"repository_url": run.repository_url, "branch": run.branch_name},
                )

                resolved = self._resolver.resolve(run.repository_url, run.branch_name)
                heartbeat.ensure_alive()

                metadata = resolved.metadata
                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "resolving_snapshot",
                    45,
                    "Resolved repository head commit.",
                    payload={
                        "branch_name": metadata["branch_name"],
                        "commit_sha": metadata["commit_sha"],
                        "tree_hash": metadata["tree_hash"],
                    },
                )
                heartbeat.ensure_alive()

                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "scanning_files",
                    60,
                    "Computed snapshot file counters.",
                    progress_current=metadata["files_total"],
                    progress_total=metadata["files_total"],
                    payload={
                        "files_total": metadata["files_total"],
                        "go_files_total": metadata["go_files_total"],
                        "readme_files_total": metadata["readme_files_total"],
                        "bytes_total": metadata["bytes_total"],
                    },
                )
                heartbeat.ensure_alive()

                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "creating_snapshot",
                    75,
                    "Upserting repository snapshot.",
                    payload={
                        "repository_id": run.repository_id,
                        "commit_sha": metadata["commit_sha"],
                    },
                )
                snapshot = self._snapshots.upsert_snapshot(run.repository_id, metadata)
                heartbeat.ensure_alive()

                snapshot_id = snapshot["id"]
                self._store.attach_snapshot(run.id, self._settings.worker_id, snapshot_id, metadata)

                self._store.update_progress(
                    run.id,
                    self._settings.worker_id,
                    "finalizing",
                    90,
                    "Finalizing snapshot-only index run.",
                    payload={"snapshot_id": snapshot_id},
                )
                heartbeat.ensure_alive()

                self._store.mark_succeeded(run.id, self._settings.worker_id)
                logger.info("Completed index_run=%s snapshot_id=%s", run.id, snapshot_id)

        except Exception as exc:
            error_code = _map_error_code(exc)
            logger.exception("Index run failed: index_run=%s error_code=%s", run.id, error_code)
            updated = self._store.mark_failed(
                run.id,
                self._settings.worker_id,
                error_code,
                str(exc),
            )
            if not updated:
                logger.warning("Could not mark failed; lease may have been lost for index_run=%s", run.id)
        finally:
            if resolved is not None:
                resolved.cleanup()


def main() -> None:
    setup_logging()
    stop = threading.Event()

    def _request_stop(signum, frame):
        logger.info("Stop requested by signal=%s", signum)
        stop.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    worker_id = settings.worker_id or _default_worker_id()
    worker_settings = WorkerSettings(
        worker_id=worker_id,
        poll_interval_s=settings.worker_poll_interval_s,
        heartbeat_seconds=settings.worker_heartbeat_seconds,
    )
    store = IndexRunStore(
        database_url=settings.database_url,
        schema=settings.repo_db_schema,
        lease_seconds=settings.worker_lease_seconds,
    )
    worker = IndexWorker(
        store=store,
        snapshots=RepositoryServiceClient(
            base_url=settings.repos_service_url,
            timeout_s=settings.request_timeout_s,
        ),
        resolver=SnapshotResolver(GitClient(), settings.clone_root),
        worker_settings=worker_settings,
    )

    logger.info("Index worker started worker_id=%s", worker_id)
    worker.run_forever(stop.is_set)
    logger.info("Index worker stopped worker_id=%s", worker_id)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _map_error_code(exc: Exception) -> str:
    if isinstance(exc, RepoCloneError):
        return "repository_clone_failed"

    if isinstance(exc, RepositoryServiceClientError):
        if exc.status_code == 404:
            return "repository_not_found"
        if exc.status_code == 409:
            return "snapshot_conflict"
        return "transient_infrastructure_failure"

    if isinstance(exc, LeaseLostError):
        return "worker_lease_lost"

    message = str(exc).lower()
    if "branch" in message or "commit" in message or "repository" in message:
        return "repository_resolve_failed"

    return "unknown_error"


if __name__ == "__main__":
    main()
