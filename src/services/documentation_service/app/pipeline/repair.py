from dataclasses import dataclass, field
from typing import Any

from app.pipeline.verification import VerificationFinding, VerificationReport

REPAIR_PLAN_SCHEMA_VERSION = 1
REPAIR_ATTEMPTS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SectionRepairPlan:
    section_key: str
    findings: list[VerificationFinding]

    @property
    def evidence_expansion_findings(self) -> list[VerificationFinding]:
        return [
            finding
            for finding in self.findings
            if finding_requires_targeted_retrieval(finding)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_key": self.section_key,
            "findings": [finding.to_dict() for finding in self.findings],
            "required_fixes": [
                finding.suggested_fix or finding.message
                for finding in self.findings
            ],
            "repair_actions": [
                _repair_action(finding)
                for finding in self.findings
            ],
        }


@dataclass(frozen=True)
class RepairPlan:
    documentation_run_id: str
    repair_round: int
    sections: list[SectionRepairPlan]
    unresolved_findings: list[VerificationFinding] = field(default_factory=list)

    def has_repairs(self) -> bool:
        return bool(self.sections)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPAIR_PLAN_SCHEMA_VERSION,
            "artifact_kind": "repair_plan",
            "documentation_run_id": self.documentation_run_id,
            "repair_round": self.repair_round,
            "sections": [section.to_dict() for section in self.sections],
            "unresolved_findings": [finding.to_dict() for finding in self.unresolved_findings],
            "summary": {
                "sections_total": len(self.sections),
                "repairable_findings_total": sum(len(section.findings) for section in self.sections),
                "unresolved_findings_total": len(self.unresolved_findings),
            },
        }


def build_repair_plan(report: VerificationReport) -> RepairPlan:
    by_section: dict[str, list[VerificationFinding]] = {}
    unresolved: list[VerificationFinding] = []
    for finding in report.findings:
        if finding.severity != "error":
            continue
        if finding.repairable and finding.section_key:
            by_section.setdefault(finding.section_key, []).append(finding)
        else:
            unresolved.append(finding)

    return RepairPlan(
        documentation_run_id=report.documentation_run_id,
        repair_round=report.repair_round + 1,
        sections=[
            SectionRepairPlan(section_key=section_key, findings=findings)
            for section_key, findings in sorted(by_section.items())
        ],
        unresolved_findings=unresolved,
    )


def finding_requires_targeted_retrieval(finding: VerificationFinding) -> bool:
    if finding.repair_strategy == "expand_evidence":
        return finding.category not in _RETRIEVAL_BLOCKED_CATEGORIES
    if finding.category in _RETRIEVAL_NEEDED_CATEGORIES:
        return True
    if finding.category == "unsupported_claim":
        return bool(finding.evidence_needed or finding.retrieval_hints)
    return False


_RETRIEVAL_NEEDED_CATEGORIES = {
    "missing_coverage",
    "not_enough_evidence",
    "weak_evidence",
}
_RETRIEVAL_BLOCKED_CATEGORIES = {
    "contradicted_claim",
    "wrong_scope",
    "citation_integrity",
    "output_hygiene",
    "readability",
    "duplication",
}


def _repair_action(finding: VerificationFinding) -> dict[str, Any]:
    requires_retrieval = finding_requires_targeted_retrieval(finding)
    if finding.category in _RETRIEVAL_BLOCKED_CATEGORIES:
        strategy = finding.repair_strategy or "rewrite_existing"
        retrieval_policy = "blocked"
    elif requires_retrieval:
        strategy = "expand_evidence"
        retrieval_policy = "targeted"
    else:
        strategy = finding.repair_strategy or "rewrite_existing"
        retrieval_policy = "not_needed"
    return {
        "check_id": finding.check_id,
        "category": finding.category,
        "repair_strategy": strategy,
        "requires_targeted_retrieval": requires_retrieval,
        "retrieval_policy": retrieval_policy,
    }


def build_repair_attempts_manifest(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    attempts: list[dict[str, Any]],
    plans: list[RepairPlan],
    final_report: VerificationReport,
    evidence_delta_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    repaired_sections = sorted(
        {
            attempt.get("section_key")
            for attempt in attempts
            if attempt.get("section_key")
        }
    )
    return {
        "schema_version": REPAIR_ATTEMPTS_SCHEMA_VERSION,
        "artifact_kind": "repair_attempts",
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "attempts": attempts,
        "plans": [plan.to_dict() for plan in plans],
        "evidence_delta_artifacts": evidence_delta_artifacts or [],
        "final_verification_status": final_report.status,
        "unresolved_findings": [
            finding.to_dict()
            for finding in final_report.findings
            if finding.severity == "error"
        ],
        "summary": {
            "repair_rounds_total": len(plans),
            "attempts_total": len(attempts),
            "evidence_delta_artifacts_total": len(evidence_delta_artifacts or []),
            "repaired_sections": repaired_sections,
            "unresolved_errors_total": sum(
                1 for finding in final_report.findings if finding.severity == "error"
            ),
        },
    }
