from app.pipeline.pipeline_trace import PipelineTrace, error_payload


def test_pipeline_trace_sanitizes_events_and_summarizes_failures() -> None:
    trace = PipelineTrace(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        attempt=2,
        requested_template_kind="developer_handbook",
    )
    trace.set_template_context(
        effective_template_kind="go_library_handbook",
        template_selection={"reason": "classified"},
        repository_classification={"repository_kind": "library", "api_key": "secret"},
    )
    trace.record("llm_judge_completed", retry_errors_total=1, section_key="overview")
    trace.record("pipeline_failed", stage="verifying_documentation")

    payload = trace.to_dict(status="failed")

    assert payload["schema_version"] == 1
    assert payload["effective_template_kind"] == "go_library_handbook"
    assert "api_key" not in payload["repository_classification"]
    assert payload["summary"]["failed"] is True
    assert payload["summary"]["llm_retry_errors_total"] == 1


def test_error_payload_includes_provider_details_without_sensitive_keys() -> None:
    class ProviderError(RuntimeError):
        error_code = "llm_response_empty"
        retryable = True
        status_code = None
        details = {"response_id": "resp-1", "api_key": "secret"}

    payload = error_payload(ProviderError("empty"))

    assert payload["error_code"] == "llm_response_empty"
    assert payload["retryable"] is True
    assert payload["details"] == {"response_id": "resp-1"}
