from dataclasses import dataclass

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
        return SectionGenerationOutput(
            section=GeneratedSection(
                section_key=contract.section_key,
                title=contract.title,
                ordinal=contract.ordinal,
                content_markdown=_ensure_section_heading(result.content, contract.title),
                source_count=len(contract.source_ids),
                generation=metadata,
            ),
            metadata=metadata,
        )


def _ensure_section_heading(markdown: str, title: str) -> str:
    normalized = markdown.strip()
    if not normalized:
        normalized = "No documentation content was generated."
    if normalized.startswith(f"## {title}"):
        return normalized + "\n"
    return f"## {title}\n\n{normalized}\n"
