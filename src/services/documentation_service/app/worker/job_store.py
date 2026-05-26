import json
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


class LeaseLostError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimedDocumentationRun:
    id: str
    repository_id: str
    snapshot_id: str
    source_index_run_id: str
    base_snapshot_id: str | None
    template_kind: str
    attempt: int
    max_attempts: int


class DocumentationRunStore:
    def __init__(self, database_url: str, schema: str, lease_seconds: int):
        self._database_url = database_url
        self._schema = schema
        self._lease_seconds = lease_seconds

    def claim_next(self, worker_id: str) -> ClaimedDocumentationRun | None:
        with self._connect() as conn:
            with conn.transaction():
                self._mark_exhausted_expired_runs_stale(conn)

                row = conn.execute(
                    sql.SQL(
                        """
                        WITH candidate AS (
                            SELECT dr."Id"
                            FROM {schema}.documentation_runs dr
                            WHERE (
                                dr."Status" = 'queued'
                                OR (dr."Status" = 'running' AND dr."LeaseUntil" < now())
                            )
                            AND dr."Attempt" < dr."MaxAttempts"
                            ORDER BY
                                CASE WHEN dr."Status" = 'queued' THEN 0 ELSE 1 END,
                                dr."CreatedAt"
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        UPDATE {schema}.documentation_runs dr
                        SET
                            "Status" = 'running',
                            "Stage" = 'loading_project_model',
                            "ProgressPct" = 5,
                            "ProgressCurrent" = 0,
                            "ProgressTotal" = 0,
                            "Attempt" = dr."Attempt" + 1,
                            "WorkerId" = %s,
                            "LeaseUntil" = now() + (%s::int * interval '1 second'),
                            "HeartbeatAt" = now(),
                            "StartedAt" = COALESCE(dr."StartedAt", now()),
                            "FinishedAt" = NULL,
                            "ErrorCode" = NULL,
                            "ErrorMessage" = NULL,
                            "UpdatedAt" = now()
                        FROM candidate c
                        WHERE dr."Id" = c."Id"
                        RETURNING
                            dr."Id",
                            dr."RepositoryId",
                            dr."SnapshotId",
                            dr."SourceIndexRunId",
                            dr."BaseSnapshotId",
                            dr."TemplateKind",
                            dr."Attempt",
                            dr."MaxAttempts";
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (worker_id, self._lease_seconds),
                ).fetchone()

                if row is None:
                    return None

                if row["SourceIndexRunId"] is None:
                    self._mark_invalid_claim_failed(
                        conn,
                        str(row["Id"]),
                        worker_id,
                        "validation_failed",
                        "Documentation run has no source index run.",
                    )
                    return None

                return ClaimedDocumentationRun(
                    id=str(row["Id"]),
                    repository_id=str(row["RepositoryId"]),
                    snapshot_id=str(row["SnapshotId"]),
                    source_index_run_id=str(row["SourceIndexRunId"]),
                    base_snapshot_id=str(row["BaseSnapshotId"]) if row["BaseSnapshotId"] is not None else None,
                    template_kind=row["TemplateKind"],
                    attempt=row["Attempt"],
                    max_attempts=row["MaxAttempts"],
                )

    def heartbeat(self, run_id: str, worker_id: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.documentation_runs
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
                raise LeaseLostError(f"Lease lost for documentation_run {run_id}.")

    def update_progress(
        self,
        run_id: str,
        worker_id: str,
        stage: str,
        progress_pct: int,
        progress_current: int = 0,
        progress_total: int = 0,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.documentation_runs
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
                raise LeaseLostError(f"Lease lost for documentation_run {run_id}.")

    def update_effective_template_kind(
        self,
        run_id: str,
        worker_id: str,
        effective_template_kind: str,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.documentation_runs
                    SET
                        "EffectiveTemplateKind" = %s,
                        "UpdatedAt" = now()
                    WHERE "Id" = %s
                    AND "Status" = 'running'
                    AND "WorkerId" = %s
                    AND "LeaseUntil" > now();
                    """
                ).format(schema=sql.Identifier(self._schema)),
                (effective_template_kind, run_id, worker_id),
            )

            if row.rowcount != 1:
                raise LeaseLostError(f"Lease lost for documentation_run {run_id}.")

    def mark_succeeded(
        self,
        run_id: str,
        worker_id: str,
        *,
        verification_summary: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.documentation_runs
                    SET
                        "Status" = 'succeeded',
                        "Stage" = 'completed',
                        "ProgressPct" = 100,
                        "ProgressCurrent" = 1,
                        "ProgressTotal" = 1,
                        "VerificationSummaryJson" = %s::jsonb,
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
                (
                    _json_or_none(verification_summary),
                    run_id,
                    worker_id,
                ),
            )

            if row.rowcount != 1:
                raise LeaseLostError(f"Lease lost for documentation_run {run_id}.")

    def mark_failed(
        self,
        run_id: str,
        worker_id: str,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = False,
    ) -> bool:
        with self._connect() as conn:
            if retryable:
                row = conn.execute(
                    sql.SQL(
                        """
                        UPDATE {schema}.documentation_runs
                        SET
                            "Status" = 'queued',
                            "Stage" = 'queued',
                            "ProgressPct" = 0,
                            "ProgressCurrent" = 0,
                            "ProgressTotal" = 0,
                            "ErrorCode" = %s,
                            "ErrorMessage" = %s,
                            "WorkerId" = NULL,
                            "LeaseUntil" = NULL,
                            "HeartbeatAt" = now(),
                            "FinishedAt" = NULL,
                            "UpdatedAt" = now()
                        WHERE "Id" = %s
                        AND "Status" = 'running'
                        AND "WorkerId" = %s
                        AND "Attempt" < "MaxAttempts";
                        """
                    ).format(schema=sql.Identifier(self._schema)),
                    (error_code, _truncate(error_message, 4000), run_id, worker_id),
                )

                return row.rowcount == 1

            row = conn.execute(
                sql.SQL(
                    """
                    UPDATE {schema}.documentation_runs
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

            return row.rowcount == 1

    def _connect(self):
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def _mark_exhausted_expired_runs_stale(self, conn) -> int:
        row = conn.execute(
            sql.SQL(
                """
                UPDATE {schema}.documentation_runs
                SET
                    "Status" = 'stale',
                    "Stage" = 'stale',
                    "ProgressPct" = 100,
                    "ErrorCode" = 'stale_lease_expired',
                    "ErrorMessage" = 'Documentation worker lease expired and max attempts were exhausted.',
                    "LeaseUntil" = NULL,
                    "FinishedAt" = now(),
                    "UpdatedAt" = now()
                WHERE "Status" = 'running'
                AND "LeaseUntil" < now()
                AND "Attempt" >= "MaxAttempts";
                """
            ).format(schema=sql.Identifier(self._schema))
        )
        return row.rowcount

    def _mark_invalid_claim_failed(
        self,
        conn,
        run_id: str,
        worker_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        conn.execute(
            sql.SQL(
                """
                UPDATE {schema}.documentation_runs
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


def _json_or_none(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[:max_length]
