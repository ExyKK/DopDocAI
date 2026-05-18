import json
from dataclasses import dataclass
from typing import Any

from app.pipeline.evidence import SectionEvidence
from app.pipeline.evidence_pack import EvidencePack

PROMPT_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class PromptMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
        }


@dataclass(frozen=True)
class SectionPromptContract:
    schema_version: int
    section_key: str
    title: str
    output_language: str
    messages: list[PromptMessage]
    source_ids: list[str]
    estimated_input_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "section_key": self.section_key,
            "title": self.title,
            "output_language": self.output_language,
            "source_ids": self.source_ids,
            "estimated_input_tokens": self.estimated_input_tokens,
            "messages": [message.to_dict() for message in self.messages],
        }


def build_section_prompt_contract(
    section: SectionEvidence,
    *,
    output_language: str = "ru",
) -> SectionPromptContract:
    if section.evidence_pack is None:
        raise ValueError(f"Section {section.section_key} has no evidence pack.")

    evidence_pack = section.evidence_pack
    messages = [
        PromptMessage(
            role="system",
            content=(
                "You are DopDocAI, a documentation generator for indexed software repositories. "
                "Write concise, source-grounded technical documentation. "
                "Do not invent files, commands, APIs, dependencies, or behavior that is not supported by evidence."
            ),
        ),
        PromptMessage(
            role="developer",
            content=_developer_instructions(output_language),
        ),
        PromptMessage(
            role="user",
            content=_user_payload(section, evidence_pack),
        ),
    ]
    return SectionPromptContract(
        schema_version=PROMPT_CONTRACT_VERSION,
        section_key=section.section_key,
        title=section.title,
        output_language=output_language,
        messages=messages,
        source_ids=[source.source_id for source in evidence_pack.sources],
        estimated_input_tokens=sum(_estimate_tokens(message.content) for message in messages),
    )


def build_prompt_contract_manifest(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    template_kind: str,
    contracts: list[SectionPromptContract],
) -> dict[str, Any]:
    return {
        "schema_version": PROMPT_CONTRACT_VERSION,
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "template_kind": template_kind,
        "artifact_kind": "prompt_contract_manifest",
        "sections": [contract.to_dict() for contract in contracts],
        "summary": {
            "sections_total": len(contracts),
            "estimated_input_tokens_total": sum(
                contract.estimated_input_tokens for contract in contracts
            ),
        },
    }


def _developer_instructions(output_language: str) -> str:
    language_instruction = {
        "ru": "Write the final markdown in Russian.",
        "en": "Write the final markdown in English.",
    }.get(output_language, f"Write the final markdown in {output_language}.")

    return "\n".join(
        [
            language_instruction,
            "Generate only the requested documentation section, not the whole document.",
            "Use Markdown.",
            "Every factual claim about repository behavior, files, commands, APIs, dependencies, or configuration must cite one or more source ids in square brackets, for example [S1] or [S2][S4].",
            "Use only source ids listed in the evidence pack.",
            "If evidence is weak or missing, say so explicitly and keep the section partial.",
            "Prefer precise repository terms from the evidence over generic wording.",
            "Do not include raw JSON dumps unless they are necessary to describe configuration or commands.",
        ]
    )


def _user_payload(section: SectionEvidence, evidence_pack: EvidencePack) -> str:
    payload = {
        "task": "Generate one developer handbook section.",
        "section": {
            "key": section.section_key,
            "title": section.title,
            "ordinal": section.ordinal,
        },
        "citation_rules": {
            "allowed_source_ids": [source.source_id for source in evidence_pack.sources],
            "required": True,
            "unknown_policy": "State that evidence is missing instead of guessing.",
        },
        "evidence_pack": evidence_pack.to_dict(),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _estimate_tokens(value: str) -> int:
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)
