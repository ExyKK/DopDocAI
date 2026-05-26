import json
import re
from dataclasses import dataclass
from typing import Any

from app.infra.llm_client import LlmCompletionProvider, LlmMessage
from app.pipeline.generator import GeneratedSection
from app.pipeline.llm_retry import call_llm_with_retry
from app.pipeline.prompt_contract import SectionPromptContract


@dataclass(frozen=True)
class SectionGenerationOutput:
    section: GeneratedSection
    metadata: dict[str, object]


class LlmSectionGenerator:
    def __init__(
        self,
        provider: LlmCompletionProvider,
        *,
        max_attempts: int = 3,
        retry_delay_s: float = 0.0,
    ):
        self._provider = provider
        self._max_attempts = max(1, max_attempts)
        self._retry_delay_s = max(0.0, retry_delay_s)

    def generate_section(self, contract: SectionPromptContract) -> SectionGenerationOutput:
        outcome = call_llm_with_retry(
            self._provider,
            [
                LlmMessage(role=message.role, content=message.content)
                for message in contract.messages
            ],
            metadata={
                "task": "documentation_section_generation",
                "section_key": contract.section_key,
                "template_kind": contract.template_kind,
                "source_count": str(len(contract.source_ids)),
                "estimated_input_tokens": str(contract.estimated_input_tokens),
            },
            max_attempts=self._max_attempts,
            retry_delay_s=self._retry_delay_s,
        )
        result = outcome.result
        metadata: dict[str, object] = {
            "provider": result.provider,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "latency_ms": result.latency_ms,
            "response_id": result.response_id,
            "cost_usd": result.cost_usd,
            "estimated_input_tokens": contract.estimated_input_tokens,
            "prompt_version": contract.schema_version,
            "llm_attempts_total": outcome.attempts_total,
            "llm_retry_errors": outcome.retry_errors,
        }
        processed_markdown, warnings = _post_process_section_markdown(
            result.content,
            contract.title,
            source_index=contract.source_index,
            finish_reason=result.finish_reason,
        )
        metadata["warnings"] = warnings
        metadata["quality_status"] = _quality_status(warnings)
        return SectionGenerationOutput(
            section=GeneratedSection(
                section_key=contract.section_key,
                title=contract.title,
                ordinal=contract.ordinal,
                content_markdown=processed_markdown,
                source_count=len(contract.source_ids),
                generation=metadata,
                section_spec=contract.section_spec,
            ),
            metadata=metadata,
        )

    def repair_section(
        self,
        contract: SectionPromptContract,
        *,
        current_markdown: str,
        findings: list[dict[str, Any]],
        repair_round: int,
        repair_evidence_delta: dict[str, Any] | None = None,
    ) -> SectionGenerationOutput:
        messages = _repair_messages(
            contract,
            current_markdown=current_markdown,
            findings=findings,
            repair_round=repair_round,
            repair_evidence_delta=repair_evidence_delta,
        )
        estimated_repair_input_tokens = sum(_estimate_tokens(message.content) for message in messages)
        outcome = call_llm_with_retry(
            self._provider,
            messages,
            metadata={
                "task": "documentation_section_repair",
                "section_key": contract.section_key,
                "template_kind": contract.template_kind,
                "repair_round": str(repair_round),
                "source_count": str(len(contract.source_ids)),
                "estimated_input_tokens": str(estimated_repair_input_tokens),
                "base_contract_estimated_input_tokens": str(contract.estimated_input_tokens),
                "repair_delta_sources": str(
                    len((repair_evidence_delta or {}).get("sources") or [])
                ),
            },
            max_attempts=self._max_attempts,
            retry_delay_s=self._retry_delay_s,
        )
        result = outcome.result
        metadata: dict[str, object] = {
            "provider": result.provider,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "latency_ms": result.latency_ms,
            "response_id": result.response_id,
            "cost_usd": result.cost_usd,
            "prompt_version": contract.schema_version,
            "repair_round": repair_round,
            "repair_findings_total": len(findings),
            "repair_delta_sources_total": len((repair_evidence_delta or {}).get("sources") or []),
            "estimated_input_tokens": estimated_repair_input_tokens,
            "base_contract_estimated_input_tokens": contract.estimated_input_tokens,
            "llm_attempts_total": outcome.attempts_total,
            "llm_retry_errors": outcome.retry_errors,
        }
        processed_markdown, warnings = _post_process_section_markdown(
            result.content,
            contract.title,
            source_index=contract.source_index,
            finish_reason=result.finish_reason,
        )
        metadata["warnings"] = warnings
        metadata["quality_status"] = _quality_status(warnings)
        return SectionGenerationOutput(
            section=GeneratedSection(
                section_key=contract.section_key,
                title=contract.title,
                ordinal=contract.ordinal,
                content_markdown=processed_markdown,
                source_count=len(contract.source_ids),
                generation=metadata,
                section_spec=contract.section_spec,
            ),
            metadata=metadata,
        )


def build_analysis_limitations_section(contract: SectionPromptContract) -> SectionGenerationOutput:
    prompt_payload = _json_object(contract.messages[-1].content)
    evidence_pack = prompt_payload.get("evidence_pack") if isinstance(prompt_payload, dict) else {}
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}

    source_ids = [
        source_id
        for source_id in evidence_pack.get("source_ids") or contract.source_ids
        if isinstance(source_id, str)
    ]
    citation = f" [{source_ids[0]}]" if source_ids else ""
    raw_summary = evidence_pack.get("raw_evidence_summary")
    if not isinstance(raw_summary, dict):
        raw_summary = {}
    warnings = [str(item) for item in (evidence_pack.get("warnings") or [])[:8]]

    if contract.output_language == "en":
        body = _analysis_limitations_body_en(citation, raw_summary, warnings, len(source_ids))
    else:
        body = _analysis_limitations_body_ru(citation, raw_summary, warnings, len(source_ids))

    processed_markdown, text_warnings = _post_process_section_markdown(
        body,
        contract.title,
        source_index=contract.source_index,
        finish_reason="stop",
    )
    metadata: dict[str, object] = {
        "provider": "deterministic",
        "model": "analysis_limitations_v1",
        "finish_reason": "stop",
        "prompt_tokens": 0,
        "completion_tokens": _estimate_tokens(processed_markdown),
        "total_tokens": _estimate_tokens(processed_markdown),
        "latency_ms": 0,
        "response_id": None,
        "cost_usd": None,
        "prompt_version": contract.schema_version,
        "warnings": text_warnings,
        "quality_status": _quality_status(text_warnings),
        "deterministic": True,
    }
    return SectionGenerationOutput(
        section=GeneratedSection(
            section_key=contract.section_key,
            title=contract.title,
            ordinal=contract.ordinal,
            content_markdown=processed_markdown,
            source_count=len(contract.source_ids),
            generation=metadata,
            section_spec=contract.section_spec,
        ),
        metadata=metadata,
    )


def _analysis_limitations_body_ru(
    citation: str,
    raw_summary: dict[str, Any],
    warnings: list[str],
    source_count: int,
) -> str:
    lines = [
        "Эта секция описывает ограничения автоматического анализа текущего run, а не дефекты репозитория.",
        "",
        "- Выводы документации ограничены источниками, выбранными в evidence pack; отсутствие файла, функции или команды в этих источниках не означает их отсутствие в репозитории.",
        f"- Для этой секции выбрано источников: `{source_count}`.{citation}",
    ]
    omitted = raw_summary.get("omitted_sources_total")
    truncated = raw_summary.get("truncated_sources_total")
    retrieval_error = raw_summary.get("retrieval_error")
    retrieval_query = raw_summary.get("retrieval_query")
    if omitted:
        lines.append(f"- Часть источников-кандидатов не попала в prompt из-за бюджета evidence: `{omitted}` omitted sources.{citation}")
    if truncated:
        lines.append(f"- Некоторые источники были усечены перед передачей в prompt: `{truncated}` truncated sources.{citation}")
    if retrieval_query:
        lines.append("- Для этой секции не используется общий retrieval; ограничения формируются из structured diagnostics и metadata evidence.")
    if retrieval_error:
        lines.append(f"- Retrieval сообщил ошибку: `{retrieval_error}`. Это ограничивает полноту evidence, но не доказывает отсутствие сущностей в репозитории.")
    if warnings:
        lines.append("")
        lines.append("Наблюдения по evidence:")
        for warning in warnings[:5]:
            lines.append(f"- `{warning}`.{citation}")
    return "\n".join(lines)


def _analysis_limitations_body_en(
    citation: str,
    raw_summary: dict[str, Any],
    warnings: list[str],
    source_count: int,
) -> str:
    lines = [
        "This section describes limitations of the automated analysis run, not defects in the repository.",
        "",
        "- Documentation claims are limited to the selected evidence pack; a file, function or command missing from evidence is not proof that it is missing from the repository.",
        f"- Sources selected for this section: `{source_count}`.{citation}",
    ]
    omitted = raw_summary.get("omitted_sources_total")
    truncated = raw_summary.get("truncated_sources_total")
    retrieval_error = raw_summary.get("retrieval_error")
    if omitted:
        lines.append(f"- Some candidate sources were omitted by evidence budget: `{omitted}` omitted sources.{citation}")
    if truncated:
        lines.append(f"- Some sources were truncated before prompting: `{truncated}` truncated sources.{citation}")
    if retrieval_error:
        lines.append(f"- Retrieval reported an error: `{retrieval_error}`. This limits evidence completeness but does not prove repository absence.")
    if warnings:
        lines.append("")
        lines.append("Evidence observations:")
        for warning in warnings[:5]:
            lines.append(f"- `{warning}`.{citation}")
    return "\n".join(lines)


def _repair_messages(
    contract: SectionPromptContract,
    *,
    current_markdown: str,
    findings: list[dict[str, Any]],
    repair_round: int,
    repair_evidence_delta: dict[str, Any] | None,
) -> list[LlmMessage]:
    payload = {
        "task": "Repair one generated documentation section.",
        "repair_round": repair_round,
        "section": {
            "key": contract.section_key,
            "title": contract.title,
            "ordinal": contract.ordinal,
        },
        "section_spec": contract.section_spec,
        "allowed_source_ids": contract.source_ids,
        "source_index": contract.source_index,
        "repair_evidence_delta": repair_evidence_delta,
        "current_markdown": current_markdown,
        "verification_findings": findings,
        "original_prompt_payload": contract.messages[-1].content,
    }
    return [
        LlmMessage(
            role="system",
            content=(
                "You are DopDocAI's documentation repairer. "
                "Revise a single generated section using only the provided evidence and findings."
            ),
        ),
        LlmMessage(
            role="developer",
            content="\n".join(
                [
                    "Return the section body only; do not include a heading or sources appendix.",
                    "Fix every verification finding that is repairable.",
                    "Remove unsupported or contradicted claims instead of trying to justify them.",
                    "Do not add facts, files, commands, APIs, dependencies or configuration outside the provided evidence.",
                    "Use repair_evidence_delta sources only when they directly support the missing fact; otherwise remove or mark the claim as unknown/partial.",
                    "Never use targeted retrieval to justify contradicted or wrong-scope claims.",
                    "Use only allowed source ids in citations.",
                    "If evidence is missing, state that explicitly and keep the section partial.",
                    "Keep the section focused on section_spec and avoid neighboring document intents.",
                ]
            ),
        ),
        LlmMessage(
            role="user",
            content=json_dumps(payload),
        ),
    ]


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _estimate_tokens(value: str) -> int:
    text = str(value or "")
    return max(1, (len(text) + 3) // 4) if text else 0


def _post_process_section_markdown(
    markdown: str,
    title: str,
    *,
    source_index: list[dict[str, Any]],
    finish_reason: str | None,
) -> tuple[str, list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    if finish_reason == "length":
        warnings.append(
            {
                "code": "finish_reason_length",
                "severity": "degraded",
                "message": "LLM stopped because the output token limit was reached.",
            }
        )

    body, removed_heading = _strip_leading_headings(markdown)
    if removed_heading:
        warnings.append(
            {
                "code": "leading_heading_removed",
                "severity": "info",
                "message": "Model returned a section heading despite body-only instructions.",
            }
        )

    body, removed_sources = _strip_model_sources_appendix(body)
    if removed_sources:
        warnings.append(
            {
                "code": "model_sources_appendix_removed",
                "severity": "info",
                "message": "Model returned a Sources appendix despite instructions; pipeline-owned appendix was kept.",
            }
        )

    body = body.strip()
    if not body:
        body = "No documentation content was generated."
        warnings.append(
            {
                "code": "empty_output",
                "severity": "degraded",
                "message": "LLM returned empty section content.",
            }
        )

    warnings.extend(_detect_text_warnings(body))
    appendix = _source_appendix(source_index)
    return _ensure_section_heading(f"{body}\n\n{appendix}", title), warnings


def _ensure_section_heading(markdown: str, title: str) -> str:
    normalized = markdown.strip()
    if not normalized:
        normalized = "No documentation content was generated."
    if normalized.startswith(f"## {title}"):
        return normalized + "\n"
    return f"## {title}\n\n{normalized}\n"


def _strip_leading_headings(markdown: str) -> tuple[str, bool]:
    lines = markdown.strip().splitlines()
    removed = False
    while lines:
        first = lines[0].strip()
        if not first:
            lines.pop(0)
            continue
        if re.match(r"^#{1,6}\s+\S", first):
            lines.pop(0)
            removed = True
            while lines and not lines[0].strip():
                lines.pop(0)
            continue
        break
    return "\n".join(lines).strip(), removed


def _strip_model_sources_appendix(markdown: str) -> tuple[str, bool]:
    pattern = re.compile(r"(?im)^#{2,6}\s*(sources|references|источники|ссылки)\s*$")
    matches = list(pattern.finditer(markdown or ""))
    if not matches:
        return markdown, False
    return markdown[: matches[-1].start()].rstrip(), True


def _detect_text_warnings(markdown: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if markdown.count("```") % 2:
        warnings.append(
            {
                "code": "unclosed_code_fence",
                "severity": "degraded",
                "message": "Markdown contains an unclosed fenced code block.",
            }
        )

    glued = re.search(r"\b([A-Za-zА-Яа-яЁё]{4,})\1\b", markdown)
    if glued:
        warnings.append(
            {
                "code": "repeated_glued_word",
                "severity": "degraded",
                "message": f"Possible glued repeated word: {glued.group(0)[:80]}",
            }
        )

    repeated_phrase = _find_repeated_phrase(markdown)
    if repeated_phrase is not None:
        warnings.append(
            {
                "code": "repeated_phrase",
                "severity": "degraded",
                "message": f"Possible repeated phrase: {repeated_phrase}",
            }
        )
    return warnings


def _quality_status(warnings: list[dict[str, str]]) -> str:
    if any(warning.get("severity") == "degraded" for warning in warnings):
        return "degraded"
    return "ok"


def _find_repeated_phrase(markdown: str) -> str | None:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9_./-]+", markdown.lower())
    if len(tokens) < 12:
        return None
    for size in range(3, 9):
        for index in range(0, len(tokens) - size * 2 + 1):
            left = tokens[index : index + size]
            right = tokens[index + size : index + size * 2]
            if left == right:
                return " ".join(left)
    return None


def _source_appendix(source_index: list[dict[str, Any]]) -> str:
    lines = ["### Sources"]
    if not source_index:
        lines.append("- No sources were selected for this section.")
        return "\n".join(lines)

    for source in source_index:
        source_id = _cell(source.get("source_id"))
        title = _cell(source.get("title"))
        location = _source_location(source)
        kind = _cell(source.get("source_kind"))
        suffix = f" ({kind})" if kind else ""
        if location:
            lines.append(f"- [{source_id}] {location}: {title}{suffix}")
        else:
            lines.append(f"- [{source_id}] {title}{suffix}")
    return "\n".join(lines)


def _source_location(source: dict[str, Any]) -> str:
    file_path = _cell(source.get("file_path"))
    if not file_path:
        return ""
    start_line = source.get("start_line")
    end_line = source.get("end_line")
    if start_line is None and end_line is None:
        return f"`{file_path}`"
    if end_line is None or end_line == start_line:
        return f"`{file_path}:{start_line}`"
    return f"`{file_path}:{start_line}-{end_line}`"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()
