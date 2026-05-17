import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

psycopg = pytest.importorskip("psycopg")

from app.worker.job_store import DocumentationRunStore  # noqa: E402


@pytest.fixture()
def database_url() -> str:
    value = os.getenv("DOCS_TEST_DATABASE_URL")
    if not value:
        pytest.skip("DOCS_TEST_DATABASE_URL is not set")
    return value


@pytest.fixture()
def repo_schema(database_url: str):
    schema = f"repo_docs_test_{uuid.uuid4().hex}"
    with psycopg.connect(database_url) as conn:
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(
            f'''
            CREATE TABLE "{schema}".documentation_runs (
                "Id" uuid PRIMARY KEY,
                "RepositoryId" uuid NOT NULL,
                "SnapshotId" uuid NOT NULL,
                "SourceIndexRunId" uuid NULL,
                "BaseSnapshotId" uuid NULL,
                "TemplateKind" text NOT NULL,
                "Status" text NOT NULL,
                "Stage" text NOT NULL,
                "ProgressPct" integer NOT NULL,
                "ProgressCurrent" integer NOT NULL,
                "ProgressTotal" integer NOT NULL,
                "Attempt" integer NOT NULL,
                "MaxAttempts" integer NOT NULL,
                "WorkerId" text NULL,
                "LeaseUntil" timestamptz NULL,
                "HeartbeatAt" timestamptz NULL,
                "ErrorCode" text NULL,
                "ErrorMessage" text NULL,
                "VerificationSummaryJson" jsonb NULL,
                "StartedAt" timestamptz NULL,
                "FinishedAt" timestamptz NULL,
                "UpdatedAt" timestamptz NOT NULL,
                "CreatedAt" timestamptz NOT NULL
            )
            '''
        )

    try:
        yield schema
    finally:
        with psycopg.connect(database_url) as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_claim_next_allows_only_one_worker(database_url: str, repo_schema: str) -> None:
    run_id = _insert_queued_run(database_url, repo_schema)
    store = DocumentationRunStore(database_url, repo_schema, lease_seconds=120)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(store.claim_next, ["worker-a", "worker-b"]))

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].id == str(run_id)
    assert claimed[0].attempt == 1
    assert claimed[0].template_kind == "developer_handbook"


def test_claim_next_reclaims_expired_running_run(database_url: str, repo_schema: str) -> None:
    run_id = _insert_queued_run(database_url, repo_schema, max_attempts=2)
    store = DocumentationRunStore(database_url, repo_schema, lease_seconds=120)

    first = store.claim_next("worker-a")
    assert first is not None

    _expire_run(database_url, repo_schema, run_id)

    second = store.claim_next("worker-b")
    assert second is not None
    assert second.id == str(run_id)
    assert second.attempt == 2


def test_claim_next_marks_expired_run_stale_when_attempts_are_exhausted(
    database_url: str,
    repo_schema: str,
) -> None:
    run_id = _insert_queued_run(database_url, repo_schema, max_attempts=1)
    store = DocumentationRunStore(database_url, repo_schema, lease_seconds=120)

    first = store.claim_next("worker-a")
    assert first is not None

    _expire_run(database_url, repo_schema, run_id)

    assert store.claim_next("worker-b") is None

    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            f'''
            SELECT "Status", "Stage", "ErrorCode"
            FROM "{repo_schema}".documentation_runs
            WHERE "Id" = %s
            ''',
            (run_id,),
        ).fetchone()

    assert row == ("stale", "stale", "stale_lease_expired")


def _insert_queued_run(
    database_url: str,
    schema: str,
    *,
    max_attempts: int = 3,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    with psycopg.connect(database_url) as conn:
        conn.execute(
            f'''
            INSERT INTO "{schema}".documentation_runs
                (
                    "Id",
                    "RepositoryId",
                    "SnapshotId",
                    "SourceIndexRunId",
                    "TemplateKind",
                    "Status",
                    "Stage",
                    "ProgressPct",
                    "ProgressCurrent",
                    "ProgressTotal",
                    "Attempt",
                    "MaxAttempts",
                    "CreatedAt",
                    "UpdatedAt"
                )
            VALUES (%s, %s, %s, %s, 'developer_handbook', 'queued', 'queued', 0, 0, 0, 0, %s, now(), now())
            ''',
            (run_id, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), max_attempts),
        )
    return run_id


def _expire_run(database_url: str, schema: str, run_id: uuid.UUID) -> None:
    with psycopg.connect(database_url) as conn:
        conn.execute(
            f'''
            UPDATE "{schema}".documentation_runs
            SET "LeaseUntil" = now() - interval '1 second'
            WHERE "Id" = %s
            ''',
            (run_id,),
        )
