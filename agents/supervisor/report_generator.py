# agents/supervisor/report_generator.py

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from schemas.issue_schema import IssueCluster, IssueReport, PersonaSimulationResult, IssueSeverity
from schemas.patch_schema import UnifiedPatchSet
from schemas.report_schema import DiagnosticReport, SeverityBreakdown, VerificationResult
from schemas.persona_schema import UIAnalysis
from prompts.supervisor_prompts import REPORT_SUMMARY_SYSTEM, REPORT_SUMMARY_USER
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def report_generator_node(state: dict) -> dict:
    logger.info("report_generator.start")

    ui_analysis           = state.get("ui_analysis")
    personas              = state.get("personas", [])
    simulation_results    = state.get("verified_results") or state.get("simulation_results", [])
    issue_clusters        = state.get("issue_clusters", [])
    verified_issues       = state.get("verified_issues", [])
    unified_patch_set     = state.get("unified_patch_set")
    verification_results: list[VerificationResult] = state.get("verification_results", [])
    verification_passed   = state.get("verification_passed", False)
    correction_loop_count = state.get("correction_loop_count", 0)
    total_patches_applied = state.get("total_patches_applied", 0)
    html_source_path      = state.get("html_source_path", "unknown.html")
    ui_context            = state.get("ui_context", "General web UI")

    original_html_path    = state.get("original_html_path", html_source_path)

    sev_breakdown   = _compute_severity_breakdown(verified_issues)
    total_issues    = len(verified_issues)
    resolved_count  = sum(len(vr.issues_resolved)       for vr in verification_results)
    remaining_count = sum(len(vr.issues_remaining)      for vr in verification_results)
    regressions     = sum(len(vr.new_issues_introduced) for vr in verification_results)

    completed_count = sum(
        1 for r in simulation_results
        if getattr(r, "task_completed", False)
    )

    overall_score, executive_summary, top_recommendations = _generate_summary(
        total_issues=total_issues,
        issues_resolved=resolved_count,
        issues_remaining=remaining_count,
        completed=completed_count,
        total_personas=len(personas),
        severity_breakdown=sev_breakdown,
        clusters=issue_clusters,
        simulation_results=simulation_results,
        ui_analysis=ui_analysis,
        verification_passed=verification_passed,
    )

    report_id = f"report_{uuid.uuid4().hex[:8]}"

    if unified_patch_set is None:
        unified_patch_set = UnifiedPatchSet(
            patches=[],
            conflicts_detected=0,
            conflicts_resolved=0,
        )

    if ui_analysis is None:
        ui_analysis = UIAnalysis(
            ui_purpose="Analysis unavailable — pipeline ended before supervisor completed.",
            ui_type="unknown",
            accessibility_risk_level="high",
            detected_issues_hint=[],
            critical_paths=[],
            interactive_elements=[],
        )
        logger.warning("report_generator.ui_analysis_missing_using_stub")

    report = DiagnosticReport(
        report_id=report_id,
        timestamp=datetime.utcnow(),
        html_source_path=html_source_path,
        original_html_path=original_html_path,
        ui_context=ui_context,
        correction_loop_count=correction_loop_count,
        ui_analysis=ui_analysis,
        personas=personas,
        persona_results=simulation_results,
        issue_clusters=issue_clusters,
        total_issues_found=total_issues,
        severity_breakdown=sev_breakdown,
        unified_patch_set=unified_patch_set,
        total_patches_applied=total_patches_applied,
        verification_results=verification_results,
        issues_resolved_count=resolved_count,
        issues_remaining_count=remaining_count,
        regressions_introduced=regressions,
        verification_passed=verification_passed,
        overall_score=overall_score,
        executive_summary=executive_summary,
        top_recommendations=top_recommendations,
    )

    _save_report(report)

    logger.info(
        "report_generator.complete",
        report_id=report_id,
        overall_score=overall_score,
        total_issues=total_issues,
        resolved=resolved_count,
        remaining=remaining_count,
        regressions=regressions,
        verification_passed=verification_passed,
        completed_personas=completed_count,
        total_personas=len(personas),
    )

    return {"report": report}


# ---------------------------------------------------------------------------
# LLM executive summary
# ---------------------------------------------------------------------------

def _generate_summary(
    total_issues: int,
    issues_resolved: int,
    issues_remaining: int,
    completed: int,
    total_personas: int,
    severity_breakdown: SeverityBreakdown,
    clusters: list[IssueCluster],
    simulation_results: list = None,
    ui_analysis: Optional[UIAnalysis] = None,
    verification_passed: bool = False,
) -> tuple[float, str, list[str]]:

    sev_str = (
        f"critical={severity_breakdown.critical}, high={severity_breakdown.high}, "
        f"medium={severity_breakdown.medium}, low={severity_breakdown.low}"
    )
    clusters_summary = "\n".join(
        f"  - [{c.dominant_severity}] {c.cluster_label} ({c.issue_count} issues): "
        f"{c.representative_description}"
        for c in clusters
    )

    user = REPORT_SUMMARY_USER.format(
        ui_type=ui_analysis.ui_type if ui_analysis else "unknown",
        total_issues=total_issues,
        issues_resolved=issues_resolved,
        issues_remaining=issues_remaining,
        completed=completed,
        total_personas=total_personas,
        severity_breakdown=sev_str,
        clusters_summary=clusters_summary or "No clusters found.",
        verification_passed=verification_passed,
    )

    raw, error = _call_supervisor_llm(
        system=REPORT_SUMMARY_SYSTEM,
        user=user,
        task="report_summary",
    )

    if error:
        logger.warning("report_generator.llm_error", error=error)
        return _fallback_summary(
            total_issues, issues_remaining, severity_breakdown,
            completed, total_personas, simulation_results or []
        )

    try:
        data  = json.loads(raw)
        score = float(data.get("overall_score", 5.0))
        score = max(0.0, min(10.0, score))
        summary = data.get("executive_summary", "")
        recs    = data.get("top_recommendations", [])
        if not isinstance(recs, list):
            recs = [str(recs)]
        return score, summary, recs[:5]
    except Exception as e:
        logger.warning("report_generator.parse_error", error=str(e))
        return _fallback_summary(
            total_issues, issues_remaining, severity_breakdown,
            completed, total_personas, simulation_results or []
        )


def _fallback_summary(
    total_issues: int,
    issues_remaining: int,
    sev: SeverityBreakdown,
    completed: int = 0,
    total_personas: int = 0,
    simulation_results: list = None,
) -> tuple[float, str, list[str]]:
    simulation_results = simulation_results or []
    task_completed_ratio = completed / max(total_personas, 1)

    if total_issues == 0:
        if task_completed_ratio >= 0.5:
            score = 9.0
            summary = (
                "No usability or accessibility issues were detected during simulation "
                f"and {completed}/{total_personas} persona(s) completed their tasks. "
                "The UI appears well-structured and accessible."
            )
            recs = ["No immediate actions required. Schedule periodic re-evaluation as the UI evolves."]
        else:
            score = 5.0
            summary = (
                f"No usability or accessibility issues were automatically detected, "
                f"but only {completed}/{total_personas} persona(s) completed their tasks. "
                "This discrepancy suggests the automated issue detection may have missed "
                "problems that blocked task completion. A manual accessibility audit is "
                "strongly recommended before deployment."
            )
            recs = [
                "Conduct a manual accessibility audit — automated detection may have missed issues.",
                "Test the UI with real users or assistive technologies (screen reader, keyboard-only).",
                "Check for missing form labels (WCAG 1.3.1) and insufficient color contrast (WCAG 1.4.3).",
                "Verify that all form submission flows provide clear success/error feedback.",
                "Review the persona simulation traces to identify where tasks were blocked.",
            ]
    else:
        resolved_ratio = 1.0 - (issues_remaining / max(total_issues, 1))
        base_score = 4.0 + resolved_ratio * 5.0 - sev.critical * 1.5 - sev.high * 0.5
        if task_completed_ratio < 0.5:
            base_score -= 1.0
        score = max(1.0, min(9.0, base_score))
        summary = (
            f"The UI evaluation found {total_issues} issues across all simulated personas "
            f"({sev.critical} critical, {sev.high} high severity). "
            f"{completed}/{total_personas} persona(s) completed their tasks. "
            f"After patching, {issues_remaining} issues remain unresolved. "
            "A full manual review of remaining issues is recommended before deployment."
        )
        recs = [
            f"Address the {sev.critical} critical issue(s) immediately before release.",
            f"Review and fix the {sev.high} high severity issue(s) to reduce user friction.",
            "Run additional persona simulations after applying manual fixes.",
            "Conduct accessibility audit with a screen reader on the patched UI.",
            "Add automated accessibility tests (axe-core) to the CI/CD pipeline.",
        ]

    return round(score, 1), summary, recs


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _compute_severity_breakdown(issues: list[IssueReport]) -> SeverityBreakdown:
    counts = Counter(str(iss.severity) for iss in issues)
    return SeverityBreakdown(
        critical=counts.get("critical", 0),
        high=counts.get("high", 0),
        medium=counts.get("medium", 0),
        low=counts.get("low", 0),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_report(report: DiagnosticReport) -> None:
    try:
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{report.report_id}.json"
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        logger.info("report_generator.saved", path=str(out_path))
    except Exception as e:
        logger.error("report_generator.save_failed", error=str(e))


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _call_supervisor_llm(
    system: str,
    user:   str,
    task:   str,
) -> tuple[str, Optional[str]]:
    return groq_chat_completion(
        api_key     = settings.supervisor_api_key,
        model       = settings.supervisor_llm_model,
        messages    = [{"role": "system", "content": system},
                       {"role": "user",   "content": user}],
        temperature = settings.supervisor_temperature,
        max_tokens  = getattr(settings, "supervisor_max_tokens", settings.llm_max_output_tokens),
        task        = task,
    )