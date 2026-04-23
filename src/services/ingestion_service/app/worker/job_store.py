import json
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class LeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimedIndexRun:
    id: str
    repository_id: str
    repository_url: str
    selected_branch: str | None
    default_branch: str | None
    attempt: int
    max_attempts: int

    @property
    def branch_name(self) -> str | None:
        return self.selected_branch or self.default_branch


class IndexRunStore:
    def __init__(self, database_url: str, schema: str, lease_seconds: int):
        self._database_url = database_url
        self._schema = schema
        self._lease_seconds = lease_seconds

    def claim_next(self, worker_id: str) -> ClaimedIndexRun | None:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        WITH candidate AS (
                            SELECT ir."Id"
                            FROM {schema}.index_runs ir
                            WHERE (
                                ir."Status" = 'queued'
                                OR (ir."Status" = 'running' AND ir."LeaseUntil" < now())
                            )
                            AND ir."Attempt" < ir."MaxAttempts"
                            ORDER BY
                                CASE WHEN ir."Status" = 'queued' THEN 0 ELSE 1 END,
                                ir."CreatedAt"
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        UPDATE {schema}.index_runs ir
                        SET
                            "Status" = 'running',
                            "Stage" = 'resolving_repository',
                            "ProgressPct" = 5,
                            "ProgressCurrent" = 0,
                            "ProgressTotal" = 0,
                            "Attempt" = ir."Attempt" + 1,
                            "WorkerId" = %s,
                            "LeaseUntil" = now() + (%s::int * interval '1 second'),
                            "HeartbeatAt" = now(),
                            "StartedAt" = COALESCE(ir."StartedAt", now()),
                            "FinishedAt" = NULL,
                            "ErrorCode" = NULL,
                            "ErrorMessage" = NULL,
                            "UpdatedAt" = now()
                        FROM candidate c, {schema}.repositories r
                        WHERE ir."Id" = c."Id"
                        AND r."Id" = ir."RepositoryId"
                        RETURNING
                            ir."Id",
                            ir."RepositoryId",
                            ir."Attempt",
                            ir."MaxAttempts",
                            r."NormalizedUrl",
                            r."SelectedBranch",
                            r."DefaultBranch";
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (worker_id, self._lease_seconds),
                ).fetchone()

                if row is None:
                    return None

                self._insert_event(
                    conn,
                    row["Id"],
                    level="info",
                    stage="resolving_repository",
                    message="Index run claimed by worker.",
                    payload={"worker_id": worker_id, "attempt": row["Attempt"]},
                )

                return ClaimedIndexRun(
                    id=str(row["Id"]),
                    repository_id=str(row["RepositoryId"]),
                    repository_url=row["NormalizedUrl"],
                    selected_branch=row["SelectedBranch"],
                    default_branch=row["DefaultBranch"],
                    attempt=row["Attempt"],
                    max_attempts=row["MaxAttempts"],
                )

    def heartbeat(self, run_id: str, worker_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.index_runs
                    SET
                        "HeartbeatAt" = now(),
                        "LeaseUntil" = now() + (%s::int * interval '1 second'),
                        "UpdatedAt" = now()
                    WHERE "Id" = %s
                    AND "Status" = 'running'
                    AND "WorkerId" = %s
                    AND "LeaseUntil" > now();
                    """
                ).format(schema=sql.Identifier(self._schema)),
                (self._lease_seconds, run_id, worker_id),
            )

            if row.rowcount != 1:
                raise LeaseLostError(f"Lease lost for index_run {run_id}.")

    def update_progress(
        self,
        run_id: str,
        worker_id: str,
        stage: str,
        progress_pct: int,
        message: str,
        progress_current: int = 0,
        progress_total: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {schema}.index_runs
                        SET
                            "Stage" = %s,
                            "ProgressPct" = %s,
                            "ProgressCurrent" = %s,
                            "ProgressTotal" = %s,
                            "UpdatedAt" = now()
                        WHERE "Id" = %s
                        AND "Status" = 'running'
                        AND "WorkerId" = %s
                        AND "LeaseUntil" > now();
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (
                        stage,
                        progress_pct,
                        progress_current,
                        progress_total,
                        run_id,
                        worker_id,
                    ),
                )

                if row.rowcount != 1:
                    raise LeaseLostError(f"Lease lost for index_run {run_id}.")

                self._insert_event(conn, run_id, "info", stage, message, payload)

    def attach_snapshot(
        self,
        run_id: str,
        worker_id: str,
        snapshot_id: str,
        metadata: dict[str, Any],
    ) -> None:
        stats = {
            "pipeline": "snapshot_resolution_only",
            "snapshot_id": snapshot_id,
            "branch_name": metadata["branch_name"],
            "commit_sha": metadata["commit_sha"],
            "tree_hash": metadata["tree_hash"],
            "files_total": metadata["files_total"],
            "go_files_total": metadata["go_files_total"],
            "readme_files_total": metadata["readme_files_total"],
            "bytes_total": metadata["bytes_total"],
        }

        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {schema}.index_runs
                        SET
                            "SnapshotId" = %s,
                            "FilesProcessed" = %s,
                            "ChunksTotal" = 0,
                            "SymbolsTotal" = 0,
                            "VectorsUpserted" = 0,
                            "StatsJson" = %s::jsonb,
                            "UpdatedAt" = now()
                        WHERE "Id" = %s
                        AND "Status" = 'running'
                        AND "WorkerId" = %s
                        AND "LeaseUntil" > now();
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (
                        snapshot_id,
                        metadata["files_total"],
                        json.dumps(stats, sort_keys=True, separators=(",", ":")),
                        run_id,
                        worker_id,
                    ),
                )

                if row.rowcount != 1:
                    raise LeaseLostError(f"Lease lost for index_run {run_id}.")

                self._insert_event(
                    conn,
                    run_id,
                    "info",
                    "creating_snapshot",
                    "Snapshot attached to index run.",
                    stats,
                )

    def mark_succeeded(self, run_id: str, worker_id: str) -> None:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {schema}.index_runs
                        SET
                            "Status" = 'succeeded',
                            "Stage" = 'completed',
                            "ProgressPct" = 100,
                            "ProgressCurrent" = 1,
                            "ProgressTotal" = 1,
                            "LeaseUntil" = NULL,
                            "HeartbeatAt" = now(),
                            "FinishedAt" = now(),
                            "UpdatedAt" = now()
                        WHERE "Id" = %s
                        AND "Status" = 'running'
                        AND "WorkerId" = %s
                        AND "LeaseUntil" > now();
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (run_id, worker_id),
                )

                if row.rowcount != 1:
                    raise LeaseLostError(f"Lease lost for index_run {run_id}.")

                self._insert_event(
                    conn,
                    run_id,
                    "info",
                    "completed",
                    "Index run completed after snapshot resolution stub.",
                    None,
                )

    def mark_failed(self, run_id: str, worker_id: str, error_code: str, error_message: str) -> bool:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {schema}.index_runs
                        SET
                            "Status" = 'failed',
                            "Stage" = 'failed',
                            "ProgressPct" = 100,
                            "ErrorCode" = %s,
                            "ErrorMessage" = %s,
                            "LeaseUntil" = NULL,
                            "HeartbeatAt" = now(),
                            "FinishedAt" = now(),
                            "UpdatedAt" = now()
                        WHERE "Id" = %s
                        AND "Status" = 'running'
                        AND "WorkerId" = %s;
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (error_code, _truncate(error_message, 4000), run_id, worker_id),
                )

                if row.rowcount != 1:
                    return False

                self._insert_event(
                    conn,
                    run_id,
                    "error",
                    "failed",
                    "Index run failed.",
                    {"error_code": error_code, "error_message": _truncate(error_message, 1000)},
                )
                return True

    def _connect(self):
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _insert_event(
        self,
        conn,
        run_id,
        level: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None,
    ) -> None:
        payload_json = None
        if payload is not None:
            payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

        conn.execute(
            sql.SQL(
                """
                INSERT INTO {schema}.index_run_events
                    ("IndexRunId", "Level", "Stage", "Message", "PayloadJson", "CreatedAt")
                VALUES (%s, %s, %s, %s, %s::jsonb, now());
                """
            ).format(schema=sql.Identifier(self._schema)),
            (run_id, level, stage, message, payload_json),
        )


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[:max_length]
