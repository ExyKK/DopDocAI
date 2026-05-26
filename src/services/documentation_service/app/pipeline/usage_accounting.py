from dataclasses import dataclass
from typing import Any

from app.pipeline.generator import GeneratedSection
from app.pipeline.verification import JudgeCallMetadata, VerificationReport

USAGE_ACCOUNTING_SCHEMA_VERSION = 1
DRIFT_RATIO_THRESHOLD = 0.25
DRIFT_TOKEN_THRESHOLD = 512


@dataclass(frozen=True)
class UsagePricing:
    prompt_usd_per_million: float | None = None
    completion_usd_per_million: float | None = None
    source: str | None = None


def generation_usage_record(
    section: GeneratedSection,
    *,
    task: str,
    repair_round: int = 0,
) -> dict[str, Any]:
    generation = section.generation or {}
    stage = "repair_generation" if task == "documentation_section_repair" else "generation"
    return _normalize_call_record(
        {
            "stage": stage,
            "task": task,
            "section_key": section.section_key,
            "document_scope": None,
            "repair_round": repair_round,
            "provider": generation.get("provider"),
            "model": generation.get("model"),
            "response_id": generation.get("response_id"),
            "finish_reason": generation.get("finish_reason"),
            "prompt_tokens": generation.get("prompt_tokens"),
            "completion_tokens": generation.get("completion_tokens"),
            "total_tokens": generation.get("total_tokens"),
            "estimated_input_tokens": generation.get("estimated_input_tokens"),
            "latency_ms": generation.get("latency_ms"),
            "attempts_total": generation.get("llm_attempts_total"),
            "retry_errors_total": _len_list(generation.get("llm_retry_errors")),
            "quality_status": generation.get("quality_status"),
            "cost_usd": generation.get("cost_usd"),
            "source_count": section.source_count,
        }
    )


def judge_usage_records(report: VerificationReport) -> list[dict[str, Any]]:
    stage = "verification_initial" if report.repair_round == 0 else "verification_post_repair"
    phase = "initial" if report.repair_round == 0 else "post_repair"
    return [
        judge_usage_record(call, stage=stage, phase=phase, repair_round=report.repair_round)
        for call in report.judge_calls
    ]


def judge_usage_record(
    call: JudgeCallMetadata,
    *,
    stage: str,
    phase: str,
    repair_round: int,
) -> dict[str, Any]:
    section_key = call.scope.removeprefix("section:") if call.scope.startswith("section:") else None
    task = (
        "documentation_document_set_verification"
        if call.scope == "document_set"
        else "documentation_section_verification"
    )
    return _normalize_call_record(
        {
            "stage": stage,
            "task": task,
            "section_key": section_key,
            "document_scope": call.scope if call.scope == "document_set" else None,
            "repair_round": repair_round,
            "verification_phase": phase,
            "provider": call.provider,
            "model": call.model,
            "response_id": call.response_id,
            "finish_reason": call.finish_reason,
            "prompt_tokens": call.prompt_tokens,
            "completion_tokens": call.completion_tokens,
            "total_tokens": call.total_tokens,
            "estimated_input_tokens": call.estimated_input_tokens,
            "latency_ms": call.latency_ms,
            "attempts_total": call.attempts_total,
            "retry_errors_total": len(call.retry_errors or []),
            "quality_status": None,
            "cost_usd": call.cost_usd,
            "source_count": None,
        }
    )


def repair_retrieval_usage_records(manifests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest in manifests:
        repair_round = _int_or_none(manifest.get("repair_round"))
        for section in manifest.get("sections") or []:
            if not isinstance(section, dict):
                continue
            summary = section.get("summary") if isinstance(section.get("summary"), dict) else {}
            records.append(
                {
                    "stage": "repair_retrieval",
                    "task": "documentation_repair_retrieval",
                    "section_key": section.get("section_key"),
                    "repair_round": repair_round,
                    "queries_total": summary.get("queries_total"),
                    "sources_added_total": summary.get("sources_added_total"),
                    "findings_total": summary.get("findings_total"),
                    "findings_requesting_retrieval_total": summary.get(
                        "findings_requesting_retrieval_total"
                    ),
                    "budget": summary.get("budget"),
                }
            )
    return records


def build_usage_accounting_report(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    attempt: int,
    requested_template_kind: str,
    effective_template_kind: str,
    generation_records: list[dict[str, Any]],
    verification_reports: list[VerificationReport],
    repair_evidence_delta_manifests: list[dict[str, Any]],
    final_report: VerificationReport,
    pricing: UsagePricing | None = None,
) -> dict[str, Any]:
    judge_records = [
        record
        for report in verification_reports
        for record in judge_usage_records(report)
    ]
    retrieval_records = repair_retrieval_usage_records(repair_evidence_delta_manifests)
    call_records = [*_normalize_records(generation_records), *judge_records]
    section_quality = _section_quality(generation_records)
    summary = summarize_usage(
        call_records=call_records,
        retrieval_records=retrieval_records,
        final_report=final_report,
        pricing=pricing,
    )
    return {
        "schema_version": USAGE_ACCOUNTING_SCHEMA_VERSION,
        "artifact_kind": "usage_accounting",
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "attempt": attempt,
        "requested_template_kind": requested_template_kind,
        "effective_template_kind": effective_template_kind,
        "summary": summary,
        "by_stage": _aggregate_by(call_records, "stage"),
        "by_task": _aggregate_by(call_records, "task"),
        "by_section": _aggregate_by(call_records, "section_key"),
        "by_model": _aggregate_by(call_records, "model"),
        "section_quality": section_quality,
        "estimation_drift": _drift_summary(call_records),
        "repair_retrieval": {
            "records": retrieval_records,
            "summary": _repair_retrieval_summary(retrieval_records),
        },
        "llm_calls": call_records,
    }


def summarize_usage(
    *,
    call_records: list[dict[str, Any]],
    retrieval_records: list[dict[str, Any]],
    final_report: VerificationReport,
    pricing: UsagePricing | None = None,
) -> dict[str, Any]:
    totals = _usage_totals(call_records)
    drift = _drift_summary(call_records)
    return {
        "llm_calls_total": len(call_records),
        "prompt_tokens": totals["prompt_tokens"],
        "completion_tokens": totals["completion_tokens"],
        "total_tokens": totals["total_tokens"],
        "estimated_input_tokens": totals["estimated_input_tokens"],
        "latency_ms": totals["latency_ms"],
        "cost": _cost_summary(call_records, pricing),
        "stages": _compact_stage_table(call_records, retrieval_records),
        "models": _providers_models(call_records),
        "repair_retrieval": _repair_retrieval_summary(retrieval_records),
        "estimation_drift": {
            "records_with_estimate_total": drift["records_with_estimate_total"],
            "large_drift_total": drift["large_drift_total"],
            "large_drift_records": drift["large_drift_records"][:8],
        },
        "verification": {
            "status": final_report.status,
            "repair_round": final_report.repair_round,
            "failed_sections": final_report.summary().get("failed_sections") or [],
            "warning_sections": final_report.summary().get("warning_sections") or [],
            "errors_total": final_report.summary().get("errors_total"),
            "warnings_total": final_report.summary().get("warnings_total"),
        },
    }


def compact_usage_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    return {
        "schema_version": report.get("schema_version"),
        "artifact_kind": report.get("artifact_kind"),
        "llm_calls_total": summary.get("llm_calls_total"),
        "prompt_tokens": summary.get("prompt_tokens"),
        "completion_tokens": summary.get("completion_tokens"),
        "total_tokens": summary.get("total_tokens"),
        "estimated_input_tokens": summary.get("estimated_input_tokens"),
        "latency_ms": summary.get("latency_ms"),
        "cost": summary.get("cost"),
        "stages": summary.get("stages"),
        "models": summary.get("models"),
        "estimation_drift": summary.get("estimation_drift"),
        "repair_retrieval": summary.get("repair_retrieval"),
        "verification": summary.get("verification"),
    }


def _normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_call_record(record) for record in records]


def _normalize_call_record(record: dict[str, Any]) -> dict[str, Any]:
    prompt_tokens = _int_or_none(record.get("prompt_tokens"))
    completion_tokens = _int_or_none(record.get("completion_tokens"))
    total_tokens = _int_or_none(record.get("total_tokens"))
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
    estimated_input_tokens = _int_or_none(record.get("estimated_input_tokens"))
    normalized = {
        **record,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_input_tokens": estimated_input_tokens,
        "latency_ms": _int_or_none(record.get("latency_ms")),
        "attempts_total": _int_or_none(record.get("attempts_total")),
        "retry_errors_total": _int_or_none(record.get("retry_errors_total")),
        "source_count": _int_or_none(record.get("source_count")),
        "cost_usd": _float_or_none(record.get("cost_usd")),
    }
    drift = _estimation_drift(estimated_input_tokens, prompt_tokens)
    if drift is not None:
        normalized["estimation_drift"] = drift
    return normalized


def _usage_totals(records: list[dict[str, Any]]) -> dict[str, int | None]:
    return {
        "prompt_tokens": _sum_int(record.get("prompt_tokens") for record in records),
        "completion_tokens": _sum_int(record.get("completion_tokens") for record in records),
        "total_tokens": _sum_int(record.get("total_tokens") for record in records),
        "estimated_input_tokens": _sum_int(record.get("estimated_input_tokens") for record in records),
        "latency_ms": _sum_int(record.get("latency_ms") for record in records),
    }


def _aggregate_by(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        value = record.get(key)
        group_key = str(value) if value else "_none"
        groups.setdefault(group_key, []).append(record)
    return {
        group_key: {
            "calls_total": len(items),
            **_usage_totals(items),
            "retry_errors_total": _sum_int(item.get("retry_errors_total") for item in items),
            "large_estimation_drift_total": sum(
                1
                for item in items
                if (item.get("estimation_drift") or {}).get("large_drift") is True
            ),
        }
        for group_key, items in sorted(groups.items())
    }


def _compact_stage_table(
    records: list[dict[str, Any]],
    retrieval_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_stage = _aggregate_by(records, "stage")
    retrieval_summary = _repair_retrieval_summary(retrieval_records)
    result: list[dict[str, Any]] = []
    for stage in (
        "generation",
        "verification_initial",
        "repair_generation",
        "repair_retrieval",
        "verification_post_repair",
        "document_assembly",
    ):
        if stage in by_stage:
            result.append({"stage": stage, **by_stage[stage]})
        elif stage == "repair_retrieval":
            result.append(
                {
                    "stage": stage,
                    "calls_total": 0,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "estimated_input_tokens": None,
                    "latency_ms": None,
                    "retry_errors_total": None,
                    "large_estimation_drift_total": 0,
                    **retrieval_summary,
                }
            )
        elif stage == "document_assembly":
            result.append(
                {
                    "stage": stage,
                    "calls_total": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_input_tokens": None,
                    "latency_ms": None,
                    "retry_errors_total": None,
                    "large_estimation_drift_total": 0,
                }
            )
    for stage, values in by_stage.items():
        if stage not in {item["stage"] for item in result}:
            result.append({"stage": stage, **values})
    return result


def _providers_models(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for record in records:
        key = (_optional_str(record.get("provider")), _optional_str(record.get("model")))
        entry = result.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "calls_total": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 0,
            },
        )
        entry["calls_total"] += 1
        entry["prompt_tokens"] += int(record.get("prompt_tokens") or 0)
        entry["completion_tokens"] += int(record.get("completion_tokens") or 0)
        entry["total_tokens"] += int(record.get("total_tokens") or 0)
        entry["latency_ms"] += int(record.get("latency_ms") or 0)
    return list(result.values())


def _section_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_section: dict[str, dict[str, Any]] = {}
    for record in records:
        section_key = _optional_str(record.get("section_key"))
        if not section_key:
            continue
        entry = by_section.setdefault(
            section_key,
            {
                "quality_status": None,
                "generation_calls_total": 0,
                "repair_calls_total": 0,
                "latest_finish_reason": None,
                "latest_model": None,
                "latest_provider": None,
            },
        )
        task = record.get("task")
        if task == "documentation_section_repair":
            entry["repair_calls_total"] += 1
        else:
            entry["generation_calls_total"] += 1
        entry["quality_status"] = record.get("quality_status") or entry["quality_status"]
        entry["latest_finish_reason"] = record.get("finish_reason")
        entry["latest_model"] = record.get("model")
        entry["latest_provider"] = record.get("provider")
    return by_section


def _drift_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    drift_records = [
        {
            "stage": record.get("stage"),
            "task": record.get("task"),
            "section_key": record.get("section_key"),
            "repair_round": record.get("repair_round"),
            "estimated_input_tokens": (record.get("estimation_drift") or {}).get(
                "estimated_input_tokens"
            ),
            "actual_prompt_tokens": (record.get("estimation_drift") or {}).get(
                "actual_prompt_tokens"
            ),
            "delta_tokens": (record.get("estimation_drift") or {}).get("delta_tokens"),
            "delta_ratio": (record.get("estimation_drift") or {}).get("delta_ratio"),
            "classification": (record.get("estimation_drift") or {}).get("classification"),
        }
        for record in records
        if (record.get("estimation_drift") or {}).get("large_drift") is True
    ]
    return {
        "records_with_estimate_total": sum(
            1 for record in records if record.get("estimation_drift") is not None
        ),
        "large_drift_total": len(drift_records),
        "large_drift_records": drift_records,
    }


def _estimation_drift(
    estimated_input_tokens: int | None,
    actual_prompt_tokens: int | None,
) -> dict[str, Any] | None:
    if estimated_input_tokens is None or actual_prompt_tokens is None:
        return None
    delta = actual_prompt_tokens - estimated_input_tokens
    denominator = max(1, estimated_input_tokens)
    ratio = delta / denominator
    large = abs(delta) >= DRIFT_TOKEN_THRESHOLD and abs(ratio) >= DRIFT_RATIO_THRESHOLD
    classification = "ok"
    if large and delta > 0:
        classification = "large_underestimate"
    elif large and delta < 0:
        classification = "large_overestimate"
    return {
        "estimated_input_tokens": estimated_input_tokens,
        "actual_prompt_tokens": actual_prompt_tokens,
        "delta_tokens": delta,
        "delta_ratio": round(ratio, 4),
        "large_drift": large,
        "classification": classification,
    }


def _cost_summary(records: list[dict[str, Any]], pricing: UsagePricing | None) -> dict[str, Any]:
    actual_cost = _sum_float(record.get("cost_usd") for record in records)
    calculated_max_cost = None
    if pricing and (
        pricing.prompt_usd_per_million is not None
        or pricing.completion_usd_per_million is not None
    ):
        prompt_tokens = sum(int(record.get("prompt_tokens") or 0) for record in records)
        completion_tokens = sum(int(record.get("completion_tokens") or 0) for record in records)
        calculated_max_cost = (
            prompt_tokens * float(pricing.prompt_usd_per_million or 0) / 1_000_000
            + completion_tokens * float(pricing.completion_usd_per_million or 0) / 1_000_000
        )

    if actual_cost is not None:
        source = "provider_usage_cost"
    elif calculated_max_cost is not None:
        source = pricing.source or "configured_provider_max_price"
    else:
        source = "unknown"
    return {
        "actual_cost_usd": _round_money(actual_cost),
        "estimated_max_cost_usd": _round_money(calculated_max_cost),
        "source": source,
        "pricing": {
            "prompt_usd_per_million": pricing.prompt_usd_per_million if pricing else None,
            "completion_usd_per_million": pricing.completion_usd_per_million if pricing else None,
            "source": pricing.source if pricing else None,
        },
    }


def _repair_retrieval_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sections_total": len(records),
        "queries_total": _sum_int(record.get("queries_total") for record in records),
        "sources_added_total": _sum_int(record.get("sources_added_total") for record in records),
        "findings_requesting_retrieval_total": _sum_int(
            record.get("findings_requesting_retrieval_total") for record in records
        ),
    }


def _sum_int(values: Any) -> int | None:
    total = 0
    seen = False
    for value in values:
        number = _int_or_none(value)
        if number is None:
            continue
        total += number
        seen = True
    return total if seen else None


def _sum_float(values: Any) -> float | None:
    total = 0.0
    seen = False
    for value in values:
        number = _float_or_none(value)
        if number is None:
            continue
        total += number
        seen = True
    return total if seen else None


def _len_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _round_money(value: float | None) -> float | None:
    return round(value, 8) if value is not None else None
