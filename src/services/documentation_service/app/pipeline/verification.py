import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.infra.llm_client import LlmCompletionProvider, LlmMessage, LlmProviderError
from app.pipeline.generator import GeneratedDocument, GeneratedSection
from app.pipeline.llm_retry import call_llm_with_retry
from app.pipeline.prompt_contract import SectionPromptContract

VerificationMode = Literal["deterministic", "llm", "hybrid"]
VerificationStatus = Literal["passed", "passed_with_warnings", "failed"]

VERIFICATION_REPORT_SCHEMA_VERSION = 1
_CITATION_RE = re.compile(r"\[(S\d+)\]")
_SHA_RE = re.compile(r"\b[0-9a-f]{10,40}\b", re.IGNORECASE)


class DocumentationVerificationError(RuntimeError):
    def __init__(self, message: str, *, report: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = "documentation_verification_failed"
        self.retryable = False
        self.report = report or {}


@dataclass(frozen=True)
class VerificationFinding:
    check_id: str
    severity: str
    category: str
    message: str
    section_key: str | None = None
    document_key: str | None = None
    claim: str | None = None
    source_ids: list[str] = field(default_factory=list)
    repairable: bool = False
    suggested_fix: str | None = None
    evidence_needed: str | None = None
    repair_strategy: str | None = None
    retrieval_hints: list[str] = field(default_factory=list)
    confidence: float | None = None
    normalization: dict[str, Any] | None = None
    origin: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "section_key": self.section_key,
            "document_key": self.document_key,
            "claim": self.claim,
            "source_ids": self.source_ids,
            "repairable": self.repairable,
            "suggested_fix": self.suggested_fix,
            "evidence_needed": self.evidence_needed,
            "repair_strategy": self.repair_strategy,
            "retrieval_hints": self.retrieval_hints,
            "confidence": self.confidence,
            "normalization": self.normalization,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class JudgeCallMetadata:
    scope: str
    provider: str
    model: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    response_id: str | None = None
    cost_usd: float | None = None
    estimated_input_tokens: int | None = None
    attempts_total: int = 1
    retry_errors: list[dict[str, Any]] = field(default_factory=list)
    response_format: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "response_id": self.response_id,
            "cost_usd": self.cost_usd,
            "estimated_input_tokens": self.estimated_input_tokens,
            "attempts_total": self.attempts_total,
            "retry_errors": self.retry_errors,
            "response_format": self.response_format,
        }


@dataclass(frozen=True)
class VerificationReport:
    documentation_run_id: str
    repository_id: str
    snapshot_id: str
    template_kind: str
    requested_template_kind: str
    mode: VerificationMode
    effective_mode: VerificationMode
    repair_round: int
    findings: list[VerificationFinding]
    judge_calls: list[JudgeCallMetadata] = field(default_factory=list)
    section_scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    document_scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    judge_normalizations: list[dict[str, Any]] = field(default_factory=list)
    carried_over_judge_sections: list[str] = field(default_factory=list)

    @property
    def status(self) -> VerificationStatus:
        if any(finding.severity == "error" for finding in self.findings):
            return "failed"
        if any(finding.severity == "warning" for finding in self.findings):
            return "passed_with_warnings"
        return "passed"

    def has_hard_errors(self) -> bool:
        return self.status == "failed"

    def summary(self) -> dict[str, Any]:
        errors = [finding for finding in self.findings if finding.severity == "error"]
        warnings = [finding for finding in self.findings if finding.severity == "warning"]
        infos = [finding for finding in self.findings if finding.severity == "info"]
        return {
            "schema_version": VERIFICATION_REPORT_SCHEMA_VERSION,
            "status": self.status,
            "mode": self.mode,
            "effective_mode": self.effective_mode,
            "repair_round": self.repair_round,
            "errors_total": len(errors),
            "warnings_total": len(warnings),
            "infos_total": len(infos),
            "repairable_errors_total": sum(1 for finding in errors if finding.repairable),
            "non_repairable_errors_total": sum(1 for finding in errors if not finding.repairable),
            "judge_calls_total": len(self.judge_calls),
            "judge_prompt_tokens": _sum_int(call.prompt_tokens for call in self.judge_calls),
            "judge_completion_tokens": _sum_int(call.completion_tokens for call in self.judge_calls),
            "judge_total_tokens": _sum_int(call.total_tokens for call in self.judge_calls),
            "judge_latency_ms": _sum_int(call.latency_ms for call in self.judge_calls),
            "judge_normalizations_total": len(self.judge_normalizations),
            "carried_over_judge_sections_total": len(set(self.carried_over_judge_sections)),
            "carried_over_judge_sections": sorted(set(self.carried_over_judge_sections)),
            "failed_sections": sorted(
                {
                    finding.section_key
                    for finding in errors
                    if finding.section_key
                }
            ),
            "warning_sections": sorted(
                {
                    finding.section_key
                    for finding in warnings
                    if finding.section_key
                }
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": VERIFICATION_REPORT_SCHEMA_VERSION,
            "artifact_kind": "verification_report",
            "documentation_run_id": self.documentation_run_id,
            "repository_id": self.repository_id,
            "snapshot_id": self.snapshot_id,
            "template_kind": self.template_kind,
            "requested_template_kind": self.requested_template_kind,
            "mode": self.mode,
            "effective_mode": self.effective_mode,
            "repair_round": self.repair_round,
            "status": self.status,
            "summary": self.summary(),
            "findings": [finding.to_dict() for finding in self.findings],
            "section_scores": self.section_scores,
            "document_scores": self.document_scores,
            "judge_calls": [call.to_dict() for call in self.judge_calls],
            "judge_normalizations": self.judge_normalizations,
            "carried_over_judge_sections": sorted(set(self.carried_over_judge_sections)),
        }


class DocumentationVerifier:
    def __init__(
        self,
        provider: LlmCompletionProvider,
        *,
        mode: VerificationMode = "hybrid",
        max_attempts: int = 3,
        retry_delay_s: float = 0.0,
        json_mode_enabled: bool = True,
    ):
        self._provider = provider
        self._mode = mode
        self._max_attempts = max(1, max_attempts)
        self._retry_delay_s = max(0.0, retry_delay_s)
        self._json_mode_enabled = json_mode_enabled

    def verify(
        self,
        *,
        documentation_run_id: str,
        repository_id: str,
        snapshot_id: str,
        template_kind: str,
        requested_template_kind: str,
        sections: list[GeneratedSection],
        documents: list[GeneratedDocument],
        manifest: dict[str, Any],
        contracts: list[SectionPromptContract],
        repair_round: int = 0,
        previous_report: VerificationReport | None = None,
        judge_section_keys: set[str] | None = None,
        force_deterministic: bool = False,
    ) -> VerificationReport:
        effective_mode = "deterministic" if force_deterministic else self._effective_mode()
        contract_by_section = {contract.section_key: contract for contract in contracts}
        previous_findings = _previous_llm_findings_by_section(previous_report)
        previous_scores = dict(previous_report.section_scores) if previous_report else {}
        findings = _deterministic_findings(
            sections=sections,
            documents=documents,
            manifest=manifest,
            contracts=contract_by_section,
        )
        judge_calls: list[JudgeCallMetadata] = []
        section_scores: dict[str, dict[str, Any]] = {}
        document_scores: dict[str, dict[str, Any]] = {}
        judge_normalizations: list[dict[str, Any]] = []
        carried_over_judge_sections: list[str] = []

        if effective_mode in {"llm", "hybrid"}:
            for section in sections:
                contract = contract_by_section.get(section.section_key)
                if contract is None:
                    continue
                if not _section_requires_llm_judge(section):
                    continue
                if judge_section_keys is not None and section.section_key not in judge_section_keys:
                    carried = previous_findings.get(section.section_key, [])
                    findings.extend(carried)
                    if section.section_key in previous_scores:
                        section_scores[section.section_key] = previous_scores[section.section_key]
                    if carried or section.section_key in previous_scores:
                        carried_over_judge_sections.append(section.section_key)
                    continue
                verdict, call = self._judge_section(section, contract)
                judge_calls.append(call)
                new_findings, normalizations = _findings_from_judge(
                    verdict,
                    scope="section",
                    section_key=section.section_key,
                    max_findings=4,
                )
                findings.extend(new_findings)
                judge_normalizations.extend(normalizations)
                scores = verdict.get("scores")
                if isinstance(scores, dict):
                    section_scores[section.section_key] = scores

            verdict, call = self._judge_document_set(
                sections=sections,
                documents=documents,
                template_kind=template_kind,
            )
            judge_calls.append(call)
            new_findings, normalizations = _findings_from_judge(
                verdict,
                scope="document_set",
                section_key=None,
                max_findings=5,
            )
            findings.extend(new_findings)
            judge_normalizations.extend(normalizations)
            scores = verdict.get("scores")
            if isinstance(scores, dict):
                document_scores["document_set"] = scores

        return VerificationReport(
            documentation_run_id=documentation_run_id,
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            template_kind=template_kind,
            requested_template_kind=requested_template_kind,
            mode=self._mode,
            effective_mode=effective_mode,
            repair_round=repair_round,
            findings=findings,
            judge_calls=judge_calls,
            section_scores=section_scores,
            document_scores=document_scores,
            judge_normalizations=judge_normalizations,
            carried_over_judge_sections=carried_over_judge_sections,
        )

    def _effective_mode(self) -> VerificationMode:
        if self._mode in {"llm", "hybrid"} and self._provider.provider_name == "stub":
            return "deterministic"
        return self._mode

    def _judge_section(
        self,
        section: GeneratedSection,
        contract: SectionPromptContract,
    ) -> tuple[dict[str, Any], JudgeCallMetadata]:
        payload = _section_judge_payload(section, contract)
        response_format = _json_response_format(self._json_mode_enabled)
        outcome = call_llm_with_retry(
            self._provider,
            _judge_messages(payload),
            metadata={
                "task": "documentation_section_verification",
                "section_key": section.section_key,
                "template_kind": contract.template_kind,
                "source_count": str(len(contract.source_ids)),
                "estimated_input_tokens": str(contract.estimated_input_tokens),
            },
            response_format=response_format,
            max_attempts=self._max_attempts,
            retry_delay_s=self._retry_delay_s,
            validator=lambda result: _parse_judge_json(result.content),
            retry_message_factory=_judge_retry_message,
        )
        return outcome.parsed_value, _call_metadata(
            f"section:{section.section_key}",
            outcome.result,
            estimated_input_tokens=contract.estimated_input_tokens,
            attempts_total=outcome.attempts_total,
            retry_errors=outcome.retry_errors,
            response_format=response_format,
        )

    def _judge_document_set(
        self,
        *,
        sections: list[GeneratedSection],
        documents: list[GeneratedDocument],
        template_kind: str,
    ) -> tuple[dict[str, Any], JudgeCallMetadata]:
        payload = {
            "task": "Verify the generated documentation set across documents.",
            "template_kind": template_kind,
            "documents": [
                {
                    "document_key": document.document_key,
                    "title": document.title,
                    "description": document.description,
                    "section_keys": list(document.section_keys),
                    "content_markdown": _truncate(document.content_markdown, 12000),
                }
                for document in documents
            ],
            "sections": [
                {
                    "section_key": section.section_key,
                    "title": section.title,
                    "document_keys": list((section.section_spec or {}).get("document_keys") or []),
                    "quality_status": (section.generation or {}).get("quality_status"),
                }
                for section in sections
            ],
            "checks": [
                "repository_brief must stay short and not become a reference dump",
                "onboarding_guide must contain practical build/run/test/setup steps when evidence exists",
                "architecture_map, reference documents and change_report must not mix intent",
                "commit-derived history belongs in change_report, not current architecture docs",
                "repeated sections or contradictory cross-document claims should be reported",
            ],
        }
        response_format = _json_response_format(self._json_mode_enabled)
        outcome = call_llm_with_retry(
            self._provider,
            _judge_messages(payload),
            metadata={
                "task": "documentation_document_set_verification",
                "template_kind": template_kind,
                "source_count": str(len(sections)),
            },
            response_format=response_format,
            max_attempts=self._max_attempts,
            retry_delay_s=self._retry_delay_s,
            validator=lambda result: _parse_judge_json(result.content),
            retry_message_factory=_judge_retry_message,
        )
        return outcome.parsed_value, _call_metadata(
            "document_set",
            outcome.result,
            attempts_total=outcome.attempts_total,
            retry_errors=outcome.retry_errors,
            response_format=response_format,
        )


def _deterministic_findings(
    *,
    sections: list[GeneratedSection],
    documents: list[GeneratedDocument],
    manifest: dict[str, Any],
    contracts: dict[str, SectionPromptContract],
) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    findings.extend(_manifest_findings(manifest))
    for section in sections:
        contract = contracts.get(section.section_key)
        allowed_source_ids = set(contract.source_ids if contract else [])
        findings.extend(_section_findings(section, allowed_source_ids, contract))
    findings.extend(_document_findings(documents))
    return findings


def _manifest_findings(manifest: dict[str, Any]) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    if manifest.get("schema_version") != 2:
        findings.append(
            VerificationFinding(
                check_id="manifest_schema_version",
                severity="error",
                category="manifest_integrity",
                message="Documentation manifest must use schema_version=2.",
                repairable=False,
            )
        )
    if not isinstance(manifest.get("documents"), list) or not manifest.get("documents"):
        findings.append(
            VerificationFinding(
                check_id="manifest_documents_missing",
                severity="error",
                category="manifest_integrity",
                message="Manifest does not contain reader-facing documents.",
                repairable=False,
            )
        )
    if not isinstance(manifest.get("sections"), list) or not manifest.get("sections"):
        findings.append(
            VerificationFinding(
                check_id="manifest_sections_missing",
                severity="error",
                category="manifest_integrity",
                message="Manifest does not contain generated sections.",
                repairable=False,
            )
        )
    return findings


def _section_findings(
    section: GeneratedSection,
    allowed_source_ids: set[str],
    contract: SectionPromptContract | None,
) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    markdown = section.content_markdown or ""
    citations = _citations(markdown)
    body = _body_without_sources(markdown)
    body_citations = _citations(body)

    if len(_body_without_sources(markdown).strip()) < 40:
        findings.append(
            VerificationFinding(
                check_id="section_empty_or_too_short",
                severity="error",
                category="output_hygiene",
                section_key=section.section_key,
                message="Generated section is empty or too short to be useful.",
                repairable=True,
                suggested_fix="Regenerate the section with concrete evidence-backed content.",
            )
        )

    unknown = sorted(citation for citation in citations if citation not in allowed_source_ids)
    for citation in unknown:
        findings.append(
            VerificationFinding(
                check_id="citation_unknown_source",
                severity="error",
                category="citation_integrity",
                section_key=section.section_key,
                message=f"Section cites unknown source id [{citation}].",
                source_ids=[citation],
                repairable=True,
                suggested_fix="Remove the citation or replace it with an allowed source id.",
            )
        )

    if allowed_source_ids and not body_citations and len(body) > 160:
        findings.append(
            VerificationFinding(
                check_id="section_missing_citations",
                severity="warning",
                category="weak_grounding",
                section_key=section.section_key,
                message="Section has available evidence but no citations in the body.",
                repairable=True,
                suggested_fix="Add citations to factual claims or state that evidence is missing.",
            )
        )

    if markdown.count("```") % 2:
        findings.append(
            VerificationFinding(
                check_id="unclosed_code_fence",
                severity="error",
                category="output_hygiene",
                section_key=section.section_key,
                message="Section markdown contains an unclosed fenced code block.",
                repairable=True,
                suggested_fix="Close or remove the broken fenced code block.",
            )
        )

    if len(re.findall(r"(?im)^#{2,6}\s*(sources|references|источники|ссылки)\s*$", markdown)) > 1:
        findings.append(
            VerificationFinding(
                check_id="duplicate_sources_appendix",
                severity="error",
                category="output_hygiene",
                section_key=section.section_key,
                message="Section contains more than one Sources/References appendix.",
                repairable=True,
                suggested_fix="Keep only the pipeline-owned Sources appendix.",
                repair_strategy="rewrite_existing",
            )
        )

    unbalanced = _unbalanced_markdown_delimiters(body)
    if unbalanced:
        findings.append(
            VerificationFinding(
                check_id="unbalanced_markdown_delimiters",
                severity="error",
                category="output_hygiene",
                section_key=section.section_key,
                message=f"Section appears to contain unbalanced delimiters: {', '.join(unbalanced)}.",
                repairable=True,
                suggested_fix="Fix or remove the broken sentence/table/list item.",
                repair_strategy="rewrite_existing",
            )
        )

    if _looks_like_raw_json_dump(body):
        findings.append(
            VerificationFinding(
                check_id="raw_json_dump",
                severity="warning",
                category="readability",
                section_key=section.section_key,
                message="Section appears to contain raw JSON instead of rendered prose.",
                repairable=True,
                suggested_fix="Rewrite raw JSON as concise prose or a small table.",
            )
        )

    if section.section_key != "change_report" and _SHA_RE.search(body):
        findings.append(
            VerificationFinding(
                check_id="commit_history_wrong_scope",
                severity="warning",
                category="wrong_scope",
                section_key=section.section_key,
                message="Non-change-report section contains commit-like hashes.",
                repairable=True,
                suggested_fix="Move commit-derived observations to change_report or remove them.",
            )
        )

    findings.extend(_go_library_consumer_scope_findings(section, body, contract))
    findings.extend(_analysis_limitations_absence_findings(section, body))

    generation = section.generation or {}
    if generation.get("finish_reason") == "length":
        findings.append(
            VerificationFinding(
                check_id="finish_reason_length",
                severity="error",
                category="output_hygiene",
                section_key=section.section_key,
                message="LLM stopped because the section hit the output token limit.",
                repairable=True,
                suggested_fix="Regenerate a shorter section that covers the required points.",
            )
        )
    return findings


def _document_findings(documents: list[GeneratedDocument]) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    document_keys = {document.document_key for document in documents}
    for required in {"repository_brief", "onboarding_guide", "architecture_map", "change_report"}:
        if required not in document_keys:
            findings.append(
                VerificationFinding(
                    check_id="document_missing",
                    severity="warning",
                    category="document_structure",
                    document_key=required,
                    message=f"Expected intent-based document '{required}' was not generated.",
                    repairable=False,
                )
            )
    findings.extend(_duplicate_document_block_findings(documents))
    return findings


def _section_judge_payload(
    section: GeneratedSection,
    contract: SectionPromptContract,
) -> dict[str, Any]:
    prompt_payload = _json_object(contract.messages[-1].content)
    return {
        "task": "Verify one generated documentation section.",
        "section": {
            "key": section.section_key,
            "title": section.title,
            "ordinal": section.ordinal,
        },
        "section_spec": contract.section_spec,
        "allowed_source_ids": contract.source_ids,
        "source_index": contract.source_index[:16],
        "generated_markdown": _truncate(section.content_markdown, 9000),
        "extracted_claims": _extract_claims(section.content_markdown, limit=20),
        "rendered_evidence_pack": _compact_evidence_pack_for_judge(
            prompt_payload.get("evidence_pack", {})
        ),
        "checks": [
            "Every factual technical claim should be supported by cited evidence.",
            "Unsupported or contradicted claims about files, APIs, commands or config are errors.",
            "The section should satisfy section_spec.must_cover when evidence exists.",
            "The section should avoid section_spec.avoid and neighboring document intents.",
            "The section should be useful, specific and not just an inventory dump.",
            "For Go library/CLI repositories, consumer documentation examples must not be treated as files, entrypoints or wiring that exists inside the repository unless runtime evidence confirms it.",
        ],
    }


def _judge_messages(payload: dict[str, Any]) -> list[LlmMessage]:
    schema = {
        "status": "passed|passed_with_warnings|failed",
        "scores": {
            "groundedness": "0.0..1.0",
            "usefulness": "0.0..1.0",
            "coverage": "0.0..1.0",
            "readability": "0.0..1.0",
        },
        "findings": [
            {
                "severity": "error|warning|info",
                "category": "unsupported_claim|contradicted_claim|missing_coverage|not_enough_evidence|weak_evidence|duplication|wrong_scope|readability|other",
                "message": "short explanation",
                "claim": "optional claim text",
                "section_key": "optional section key",
                "document_key": "optional document key",
                "source_ids": ["S1"],
                "confidence": 0.0,
                "repairable": True,
                "suggested_fix": "specific correction",
                "evidence_needed": "optional missing evidence",
                "repair_strategy": "rewrite_existing|expand_evidence|remove_claim",
                "retrieval_hints": ["optional short search terms"],
            }
        ],
    }
    return [
        LlmMessage(
            role="system",
            content=(
                "You are a strict documentation verification judge. "
                "You verify generated repository documentation against provided evidence. "
                "Return JSON only and never add prose outside JSON."
            ),
        ),
        LlmMessage(
            role="developer",
            content=(
                "Validate groundedness, usefulness, coverage and scope. "
                "Treat unsupported or contradicted technical claims about files, APIs, commands, "
                "dependencies or configuration as error findings. "
                "Return at most four findings for a section and only material issues. "
                "Use short messages; do not include long reasoning or self-correction prose. "
                "Use severity=error only for confirmed unsupported_claim, contradicted_claim or wrong_scope issues. "
                "Use severity=warning for weak usefulness, duplication, weak evidence and broad missing coverage. "
                "Use severity=error for missing coverage only when the gap is precise, repair_strategy=expand_evidence, "
                "and evidence_needed/retrieval_hints identify concrete files, symbols or commands. "
                "Use repair_strategy=expand_evidence only for precise missing evidence with concrete retrieval_hints. "
                "Use repair_strategy=remove_claim for contradicted or wrong-scope claims. "
                "Use this exact JSON shape: "
                f"{json.dumps(schema, ensure_ascii=False)}"
            ),
        ),
        LlmMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str),
        ),
    ]


def _parse_judge_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LlmProviderError(
            "Verification judge returned invalid JSON.",
            error_code="verification_judge_invalid_response",
            retryable=True,
            details={"raw_response_excerpt": _truncate(stripped, 1024)},
        ) from exc
    if not isinstance(payload, dict):
        raise LlmProviderError(
            "Verification judge JSON response must be an object.",
            error_code="verification_judge_invalid_response",
            retryable=True,
            details={"raw_response_excerpt": _truncate(stripped, 1024)},
        )
    status = payload.get("status")
    if status not in {"passed", "passed_with_warnings", "failed"}:
        raise LlmProviderError(
            "Verification judge JSON response must contain a valid status.",
            error_code="verification_judge_invalid_response",
            retryable=True,
            details={"raw_response_excerpt": _truncate(stripped, 1024)},
        )
    findings = payload.get("findings")
    if findings is not None and not isinstance(findings, list):
        raise LlmProviderError(
            "Verification judge findings must be an array.",
            error_code="verification_judge_invalid_response",
            retryable=True,
            details={"raw_response_excerpt": _truncate(stripped, 1024)},
        )
    if status in {"passed_with_warnings", "failed"} and not findings:
        raise LlmProviderError(
            "Verification judge non-passing response must include findings.",
            error_code="verification_judge_invalid_response",
            retryable=True,
            details={"raw_response_excerpt": _truncate(stripped, 1024)},
        )
    return payload


def _findings_from_judge(
    payload: dict[str, Any],
    *,
    scope: str,
    section_key: str | None,
    max_findings: int,
) -> tuple[list[VerificationFinding], list[dict[str, Any]]]:
    findings: list[VerificationFinding] = []
    normalizations: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("findings") or [], start=1):
        if not isinstance(item, dict):
            continue
        if len(findings) >= max_findings:
            normalizations.append(
                {
                    "scope": scope,
                    "section_key": section_key,
                    "finding_index": index,
                    "action": "dropped",
                    "reason": "max_material_findings_exceeded",
                }
            )
            continue
        severity = _enum(item.get("severity"), {"error", "warning", "info"}, default="warning")
        category = _optional_str(item.get("category")) or "other"
        finding_section_key = _optional_str(item.get("section_key")) or section_key
        confidence = _optional_float(item.get("confidence"))
        repair_strategy = _enum(
            item.get("repair_strategy"),
            {"rewrite_existing", "expand_evidence", "remove_claim"},
            default="rewrite_existing",
        )
        evidence_needed = _optional_str(item.get("evidence_needed"))
        retrieval_hints = _string_list(item.get("retrieval_hints"), limit=5)
        severity, repairable, repair_strategy, normalization = _normalize_judge_finding(
            severity=severity,
            category=category,
            message=_optional_str(item.get("message")) or "",
            claim=_optional_str(item.get("claim")),
            suggested_fix=_optional_str(item.get("suggested_fix")),
            evidence_needed=evidence_needed,
            retrieval_hints=retrieval_hints,
            repair_strategy=repair_strategy,
            confidence=confidence,
            requested_repairable=bool(item.get("repairable", severity == "error")),
        )
        if normalization is not None:
            normalization.update(
                {
                    "scope": scope,
                    "section_key": finding_section_key,
                    "finding_index": index,
                    "category": category,
                }
            )
            normalizations.append(normalization)
        findings.append(
            VerificationFinding(
                check_id=f"llm_judge_{scope}_{index}",
                severity=severity,
                category=category,
                message=_optional_str(item.get("message")) or "LLM judge reported a verification finding.",
                section_key=finding_section_key,
                document_key=_optional_str(item.get("document_key")),
                claim=_optional_str(item.get("claim")),
                source_ids=[
                    source_id
                    for source_id in item.get("source_ids") or []
                    if isinstance(source_id, str)
                ],
                repairable=repairable,
                suggested_fix=_optional_str(item.get("suggested_fix")),
                evidence_needed=evidence_needed,
                repair_strategy=repair_strategy,
                retrieval_hints=retrieval_hints,
                confidence=confidence,
                normalization=normalization,
                origin="llm_judge",
            )
        )
    return findings, normalizations


def _call_metadata(
    scope: str,
    result: Any,
    *,
    estimated_input_tokens: int | None = None,
    attempts_total: int = 1,
    retry_errors: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
) -> JudgeCallMetadata:
    return JudgeCallMetadata(
        scope=scope,
        provider=result.provider,
        model=result.model,
        finish_reason=result.finish_reason,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        latency_ms=result.latency_ms,
        response_id=result.response_id,
        cost_usd=getattr(result, "cost_usd", None),
        estimated_input_tokens=estimated_input_tokens,
        attempts_total=attempts_total,
        retry_errors=retry_errors or [],
        response_format=response_format,
    )


def _json_response_format(enabled: bool) -> dict[str, Any] | None:
    return {"type": "json_object"} if enabled else None


def _judge_retry_message(error: LlmProviderError, attempt: int) -> LlmMessage:
    return LlmMessage(
        role="developer",
        content=(
            "Your previous verification response was invalid. "
            f"Error code: {error.error_code}. Attempt: {attempt}. "
            "Return a single valid JSON object only, without markdown fences, prose, comments or trailing text. "
            "The JSON object must include status, scores and findings fields."
        ),
    )


def _citations(markdown: str) -> set[str]:
    return set(_CITATION_RE.findall(markdown or ""))


def _body_without_sources(markdown: str) -> str:
    return (markdown or "").split("### Sources", 1)[0].strip()


def _section_requires_llm_judge(section: GeneratedSection) -> bool:
    return section.section_key != "analysis_limitations"


def _previous_llm_findings_by_section(
    report: VerificationReport | None,
) -> dict[str, list[VerificationFinding]]:
    result: dict[str, list[VerificationFinding]] = {}
    if report is None:
        return result

    for finding in report.findings:
        if finding.origin != "llm_judge" or not finding.section_key:
            continue
        result.setdefault(finding.section_key, []).append(finding)
    return result


def _compact_evidence_pack_for_judge(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    sources = value.get("sources")
    compact_sources: list[dict[str, Any]] = []
    if isinstance(sources, list):
        for source in sources[:12]:
            if not isinstance(source, dict):
                continue
            compact_sources.append(
                {
                    "source_id": source.get("source_id"),
                    "title": source.get("title"),
                    "source_kind": source.get("source_kind"),
                    "file_path": source.get("file_path"),
                    "symbol_name": source.get("symbol_name"),
                    "line_range": source.get("line_range"),
                    "source_scope": source.get("source_scope"),
                    "content_markdown": _truncate(str(source.get("content_markdown") or ""), 1400),
                }
            )

    return {
        "schema_version": value.get("schema_version"),
        "format": value.get("format"),
        "source_ids": list(value.get("source_ids") or [])[:16],
        "raw_evidence_summary": value.get("raw_evidence_summary") or {},
        "warnings": list(value.get("warnings") or [])[:12],
        "sources": compact_sources,
    }


def _extract_claims(markdown: str, *, limit: int = 32) -> list[dict[str, Any]]:
    body = _body_without_sources(markdown)
    claims: list[dict[str, Any]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip(" -*\t")
        if not line or line.startswith("#") or len(line) < 24:
            continue
        for sentence in _sentences(line):
            if not _looks_technical_claim(sentence):
                continue
            claims.append(
                {
                    "text": _truncate(sentence, 600),
                    "source_ids": sorted(_citations(sentence)),
                    "kind": _claim_kind(sentence),
                }
            )
            if len(claims) >= limit:
                return claims
    return claims


def _sentences(line: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", line).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def _looks_technical_claim(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "`",
        ".go",
        ".ts",
        ".json",
        ".yaml",
        ".yml",
        "http",
        "api",
        "command",
        "config",
        "env",
        "package",
        "module",
        "function",
        "method",
        "struct",
        "docker",
        "команд",
        "конфиг",
        "пакет",
        "модул",
        "файл",
        "api",
    )
    return any(marker in lowered for marker in markers) or bool(_citations(text))


def _claim_kind(text: str) -> str:
    lowered = text.lower()
    if "config" in lowered or "env" in lowered or "конфиг" in lowered:
        return "configuration"
    if "command" in lowered or "cmd." in lowered or "команд" in lowered:
        return "command"
    if "api" in lowered or "http" in lowered:
        return "api"
    if ".go" in lowered or "package" in lowered or "пакет" in lowered:
        return "code"
    return "technical"


def _go_library_consumer_scope_findings(
    section: GeneratedSection,
    body: str,
    contract: SectionPromptContract | None,
) -> list[VerificationFinding]:
    if contract is None or contract.template_kind != "go_library_handbook":
        return []
    if section.section_key not in {"overview", "public_api", "command_lifecycle", "build_run_test"}:
        return []

    consumer_source_ids = _consumer_example_source_ids(contract.source_index)
    findings: list[VerificationFinding] = []
    for line in body.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if "main.go" not in lowered and "cmd.execute" not in lowered:
            continue
        if _line_distinguishes_consumer_example(lowered):
            continue
        if not _line_claims_repository_scope(lowered):
            continue
        cited = sorted(_citations(stripped) & consumer_source_ids)
        findings.append(
            VerificationFinding(
                check_id="go_library_consumer_example_wrong_scope",
                severity="warning",
                category="wrong_scope",
                section_key=section.section_key,
                message=(
                    "Go library section appears to present a consumer example "
                    "as an entrypoint or implementation file in the repository."
                ),
                claim=_truncate(stripped, 600),
                source_ids=cited,
                repairable=True,
                suggested_fix=(
                    "Rewrite this as downstream usage example or remove the claim unless runtime evidence confirms it."
                ),
                repair_strategy="remove_claim",
                origin="deterministic",
            )
        )
    return findings


def _analysis_limitations_absence_findings(
    section: GeneratedSection,
    body: str,
) -> list[VerificationFinding]:
    if section.section_key not in {"analysis_limitations", "known_gaps"}:
        return []

    findings: list[VerificationFinding] = []
    for line in body.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not _line_makes_absence_claim(lowered):
            continue
        if _line_scopes_absence_to_evidence(lowered):
            continue
        findings.append(
            VerificationFinding(
                check_id="analysis_limitations_repository_absence_claim",
                severity="error",
                category="wrong_scope",
                section_key=section.section_key,
                message=(
                    "Analysis limitations section claims repository absence instead of "
                    "scoping the limitation to selected evidence."
                ),
                claim=_truncate(stripped, 600),
                repairable=True,
                suggested_fix=(
                    "Rewrite the claim as 'not present in selected evidence' or remove it."
                ),
                repair_strategy="rewrite_existing",
                origin="deterministic",
            )
        )
    return findings


def _consumer_example_source_ids(source_index: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for source in source_index:
        path = str(source.get("file_path") or "").lower()
        scope = str(source.get("source_scope") or "").lower()
        title = str(source.get("title") or "").lower()
        if (
            scope in {"docs", "documentation"}
            or path.startswith("site/content/")
            or "/examples/" in path
            or "user_guide" in path
            or "example" in title
        ):
            source_id = source.get("source_id")
            if isinstance(source_id, str) and source_id:
                result.add(source_id)
    return result


def _line_distinguishes_consumer_example(line: str) -> bool:
    return any(
        marker in line
        for marker in (
            "example",
            "consumer",
            "downstream",
            "usage",
            "пример",
            "потребител",
            "использован",
            "приложени",
        )
    )


def _line_claims_repository_scope(line: str) -> bool:
    return any(
        marker in line
        for marker in (
            "repository",
            "repo",
            "project",
            "codebase",
            "репозитор",
            "проект",
            "кодовая база",
            "entrypoint",
            "точк",
            "вход",
            "содержит",
            "contains",
        )
    )


def _line_makes_absence_claim(line: str) -> bool:
    return any(
        marker in line
        for marker in (
            "отсутств",
            "не найден",
            "не обнаруж",
            "нет файла",
            "нет функции",
            "missing from the repository",
            "not present in the repository",
            "does not exist",
            "absent from the repository",
        )
    )


def _line_scopes_absence_to_evidence(line: str) -> bool:
    return any(
        marker in line
        for marker in (
            "evidence",
            "выборк",
            "источник",
            "доказател",
            "retrieval",
            "prompt",
            "analysis run",
            "selected sources",
        )
    )


def _looks_like_raw_json_dump(markdown: str) -> bool:
    text = markdown.strip()
    if "```json" in text.lower():
        return True
    return text.count('":') >= 5 and text.count("{") >= 2 and text.count("}") >= 2


def _unbalanced_markdown_delimiters(markdown: str) -> list[str]:
    text = re.sub(r"```.*?```", "", markdown or "", flags=re.DOTALL)
    pairs = (("(", ")"), ("[", "]"))
    result: list[str] = []
    for left, right in pairs:
        delta = text.count(left) - text.count(right)
        if abs(delta) >= 2:
            result.append(f"{left}{right}")
    return result


def _duplicate_document_block_findings(documents: list[GeneratedDocument]) -> list[VerificationFinding]:
    findings: list[VerificationFinding] = []
    seen: dict[str, str] = {}
    for document in documents:
        for block in _markdown_blocks(document.content_markdown):
            owner = seen.get(block)
            if owner is None:
                seen[block] = document.document_key
                continue
            if owner == document.document_key:
                continue
            findings.append(
                VerificationFinding(
                    check_id="duplicate_document_block",
                    severity="warning",
                    category="duplication",
                    document_key=document.document_key,
                    message=(
                        "Reader-facing document repeats a substantial block already present "
                        f"in '{owner}'."
                    ),
                    repairable=False,
                    origin="deterministic",
                )
            )
            break
    return findings


def _markdown_blocks(markdown: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in (markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                block = _normalize_block("\n".join(current))
                if _is_material_block(block):
                    blocks.append(block)
                current = []
            continue
        if line.startswith("#"):
            continue
        current.append(line)
    if current:
        block = _normalize_block("\n".join(current))
        if _is_material_block(block):
            blocks.append(block)
    return blocks


def _normalize_block(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _is_material_block(value: str) -> bool:
    return len(value) >= 300 and not value.startswith("### sources")


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _enum(value: Any, allowed: set[str], *, default: str) -> str:
    text = _optional_str(value)
    return text if text in allowed else default


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _optional_str(item)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


_HARD_LLM_CATEGORIES = {
    "unsupported_claim",
    "contradicted_claim",
    "wrong_scope",
}
_WARNING_ONLY_LLM_CATEGORIES = {
    "missing_coverage",
    "weak_evidence",
    "duplication",
    "readability",
    "other",
}
_TARGETED_EVIDENCE_GAP_CATEGORIES = {
    "missing_coverage",
    "not_enough_evidence",
}
_NO_ISSUE_MARKERS = (
    "no issue",
    "no actual",
    "no contradiction",
    "actually supported",
    "already supported",
    "supported by",
    "no fix needed",
    "not an issue",
    "без ошибки",
    "нет ошибки",
    "не является ошибкой",
    "подтвержден",
    "поддержан",
)


def _normalize_judge_finding(
    *,
    severity: str,
    category: str,
    message: str,
    claim: str | None,
    suggested_fix: str | None,
    evidence_needed: str | None,
    retrieval_hints: list[str],
    repair_strategy: str,
    confidence: float | None,
    requested_repairable: bool,
) -> tuple[str, bool, str, dict[str, Any] | None]:
    normalized_severity = severity
    normalized_repairable = requested_repairable
    normalized_strategy = repair_strategy
    reasons: list[str] = []

    combined_text = " ".join(
        item for item in (message, claim or "", suggested_fix or "") if item
    ).lower()
    has_precise_evidence_target = bool(evidence_needed or retrieval_hints)
    is_targeted_evidence_gap = (
        category in _TARGETED_EVIDENCE_GAP_CATEGORIES
        and repair_strategy == "expand_evidence"
        and has_precise_evidence_target
        and (confidence is None or confidence >= 0.65)
    )

    if normalized_severity == "error" and any(marker in combined_text for marker in _NO_ISSUE_MARKERS):
        normalized_severity = "info"
        normalized_repairable = False
        normalized_strategy = "rewrite_existing"
        reasons.append("judge_message_indicates_no_material_issue")

    if (
        normalized_severity == "error"
        and category in _WARNING_ONLY_LLM_CATEGORIES
        and not is_targeted_evidence_gap
    ):
        normalized_severity = "warning"
        reasons.append("category_is_not_hard_error")

    if (
        normalized_severity == "error"
        and category not in _HARD_LLM_CATEGORIES
        and not is_targeted_evidence_gap
    ):
        normalized_severity = "warning"
        reasons.append("category_not_allowed_as_llm_hard_error")

    if normalized_severity == "error" and confidence is not None and confidence < 0.55:
        normalized_severity = "warning"
        reasons.append("low_confidence_hard_error_downgraded")

    if normalized_strategy == "expand_evidence" and category not in {
        "missing_coverage",
        "not_enough_evidence",
    }:
        normalized_strategy = "rewrite_existing"
        reasons.append("expand_evidence_disallowed_for_category")

    if normalized_severity != "error" and normalized_strategy == "expand_evidence":
        normalized_strategy = "rewrite_existing"
        reasons.append("non_error_expand_evidence_downgraded")

    if normalized_severity != "error":
        normalized_repairable = False if normalized_severity == "info" else normalized_repairable

    normalization = None
    if reasons:
        normalization = {
            "action": "normalized",
            "reasons": reasons,
            "original_severity": severity,
            "normalized_severity": normalized_severity,
            "original_repair_strategy": repair_strategy,
            "normalized_repair_strategy": normalized_strategy,
        }

    return normalized_severity, normalized_repairable, normalized_strategy, normalization


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return 0.0
    if number > 1:
        return 1.0
    return number


def _truncate(value: str, max_length: int) -> str:
    return value if len(value) <= max_length else value[:max_length]


def _sum_int(values: Any) -> int | None:
    total = 0
    seen = False
    for value in values:
        if value is None:
            continue
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
        seen = True
    return total if seen else None
