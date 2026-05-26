from app.pipeline.generator import GeneratedSection
from app.pipeline.usage_accounting import (
    UsagePricing,
    build_usage_accounting_report,
    generation_usage_record,
)
from app.pipeline.verification import JudgeCallMetadata, VerificationReport


def test_usage_accounting_sums_generation_repair_and_all_judge_rounds() -> None:
    initial = _section(
        "overview",
        provider="openrouter",
        model="model-a",
        prompt_tokens=1_000,
        completion_tokens=200,
        estimated_input_tokens=700,
    )
    repaired = _section(
        "overview",
        provider="openrouter",
        model="model-a",
        prompt_tokens=1_500,
        completion_tokens=300,
        estimated_input_tokens=1_000,
        repair_round=1,
    )
    initial_report = _report(
        repair_round=0,
        calls=[
            _judge_call("section:overview", prompt_tokens=800, completion_tokens=100, estimated=500)
        ],
    )
    repaired_report = _report(
        repair_round=1,
        calls=[
            _judge_call("document_set", prompt_tokens=600, completion_tokens=80, estimated=None)
        ],
    )

    report = build_usage_accounting_report(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        attempt=1,
        requested_template_kind="developer_handbook",
        effective_template_kind="go_library_handbook",
        generation_records=[
            generation_usage_record(initial, task="documentation_section_generation"),
            generation_usage_record(repaired, task="documentation_section_repair", repair_round=1),
        ],
        verification_reports=[initial_report, repaired_report],
        repair_evidence_delta_manifests=[
            {
                "repair_round": 1,
                "sections": [
                    {
                        "section_key": "overview",
                        "summary": {
                            "queries_total": 2,
                            "sources_added_total": 1,
                            "findings_requesting_retrieval_total": 1,
                        },
                    }
                ],
            }
        ],
        final_report=repaired_report,
        pricing=UsagePricing(
            prompt_usd_per_million=1.0,
            completion_usd_per_million=2.0,
            source="test_prices",
        ),
    )

    assert report["summary"]["prompt_tokens"] == 3_900
    assert report["summary"]["completion_tokens"] == 680
    assert report["summary"]["stages"][0]["stage"] == "generation"
    assert report["by_stage"]["repair_generation"]["calls_total"] == 1
    assert report["by_stage"]["verification_initial"]["calls_total"] == 1
    assert report["by_stage"]["verification_post_repair"]["calls_total"] == 1
    assert report["repair_retrieval"]["summary"]["queries_total"] == 2
    assert report["summary"]["cost"]["estimated_max_cost_usd"] == 0.00526
    assert report["summary"]["estimation_drift"]["large_drift_total"] >= 1


def _section(
    key: str,
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_input_tokens: int,
    repair_round: int | None = None,
) -> GeneratedSection:
    generation = {
        "provider": provider,
        "model": model,
        "finish_reason": "stop",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "estimated_input_tokens": estimated_input_tokens,
        "latency_ms": 10,
        "quality_status": "ok",
    }
    if repair_round is not None:
        generation["repair_round"] = repair_round
    return GeneratedSection(
        section_key=key,
        title=key.title(),
        ordinal=1,
        content_markdown="## Overview\n\nText [S1].",
        source_count=1,
        generation=generation,
        section_spec={"document_keys": ["repository_brief"]},
    )


def _judge_call(
    scope: str,
    *,
    prompt_tokens: int,
    completion_tokens: int,
    estimated: int | None,
) -> JudgeCallMetadata:
    return JudgeCallMetadata(
        scope=scope,
        provider="openrouter",
        model="model-a",
        finish_reason="stop",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        latency_ms=20,
        estimated_input_tokens=estimated,
    )


def _report(
    *,
    repair_round: int,
    calls: list[JudgeCallMetadata],
) -> VerificationReport:
    return VerificationReport(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        requested_template_kind="developer_handbook",
        mode="hybrid",
        effective_mode="hybrid",
        repair_round=repair_round,
        findings=[],
        judge_calls=calls,
    )
