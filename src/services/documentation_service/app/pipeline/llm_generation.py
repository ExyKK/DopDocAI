import re
from dataclasses import dataclass
from typing import Any

from app.infra.llm_client import LlmCompletionProvider, LlmMessage
from app.pipeline.generator import GeneratedSection
from app.pipeline.prompt_contract import SectionPromptContract


@dataclass(frozen=True)
class SectionGenerationOutput:
    section: GeneratedSection
    metadata: dict[str, object]


class LlmSectionGenerator:
    def __init__(self, provider: LlmCompletionProvider):
        self._provider = provider

    def generate_section(self, contract: SectionPromptContract) -> SectionGenerationOutput:
        result = self._provider.generate(
            [
                LlmMessage(role=message.role, content=message.content)
                for message in contract.messages
            ],
            metadata={
                "task": "documentation_section_generation",
                "section_key": contract.section_key,
                "template_kind": "developer_handbook",
            },
        )
        metadata: dict[str, object] = {
            "provider": result.provider,
            "model": result.model,
            "finish_reason": result.finish_reason,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "latency_ms": result.latency_ms,
            "response_id": result.response_id,
            "prompt_version": contract.schema_version,
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
            ),
            metadata=metadata,
        )


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
