from app.worker.index_worker import _with_base_snapshot_context


def test_with_base_snapshot_context_records_missing_base_reason() -> None:
    metadata = {
        "branch_name": "main",
        "commit_sha": "b" * 40,
        "tree_hash": "c" * 40,
    }

    enriched = _with_base_snapshot_context(metadata, None)

    assert enriched == {
        **metadata,
        "base_snapshot_fallback_reason": "base_snapshot_missing",
    }
    assert "base_snapshot_id" not in metadata


def test_with_base_snapshot_context_attaches_previous_snapshot() -> None:
    metadata = {
        "branch_name": "main",
        "commit_sha": "b" * 40,
        "tree_hash": "c" * 40,
    }
    previous_snapshot = {
        "id": "snapshot-a",
        "branch_name": "main",
        "commit_sha": "a" * 40,
        "tree_hash": "d" * 40,
        "created_at": "2026-04-16T12:00:00Z",
    }

    enriched = _with_base_snapshot_context(metadata, previous_snapshot)

    assert enriched["base_snapshot_id"] == "snapshot-a"
    assert enriched["base_commit_sha"] == "a" * 40
    assert enriched["base_snapshot"] == previous_snapshot
    assert "base_snapshot_fallback_reason" not in enriched
