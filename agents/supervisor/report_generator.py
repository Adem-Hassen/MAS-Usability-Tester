# tools/report/report_generator.py
"""
Report Generator Node — assembles the final DiagnosticReport.

Called as the last node in the LangGraph pipeline, after verification_passed = True
(or after max correction loops are exhausted).

Pipeline:
  1. Collect all pipeline data from state
  2. Compute summary statistics (severity breakdown, resolution counts, etc.)
  3. Call supervisor LLM to produce executive_summary + top_recommendations + overall_score
  4. Assemble DiagnosticReport Pydantic model
  5. Write JSON report to settings.output_dir / report_{report_id}.json
  6. Write patched HTML (if not already saved by patch_applicator)
  7. Return {"report": DiagnosticReport} to state

The LLM call is optional — if it fails, a deterministic fallback summary is
generated from the structured data so the pipeline always produces output.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional


from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from core.state import GraphState
from schemas.issue_schema import IssueCluster, IssueReport, PersonaSimulationResult, IssueSeverity
from schemas.patch_schema import UnifiedPatchSet
from schemas.report_schema import DiagnosticReport, SeverityBreakdown, VerificationResult
from prompts.supervisor_prompts import REPORT_SUMMARY_SYSTEM, REPORT_SUMMARY_USER
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def report_generator_node(state: GraphState) -> dict:
    """
    LangGraph node.  Assembles and persists the DiagnosticReport.
    Returns {"report": DiagnosticReport}.
    """
    logger.info("report_generator.start")

    # ── Collect state ──────────────────────────────────────────────────────
    ui_analysis        = state.get("ui_analysis")
    personas           = state.get("personas", [])
    simulation_results = state.get("verified_results") or state.get("simulation_results", [])
    issue_clusters     = state.get("issue_clusters", [])
    verified_issues    = state.get("verified_issues", [])
    unified_patch_set  = state.get("unified_patch_set")
    verification_results: list[VerificationResult] = state.get("verification_results", [])
    verification_passed = state.get("verification_passed", False)
    correction_loop_count = state.get("correction_loop_count", 0)
    total_patches_applied = state.get("total_patches_applied", 0)
    patched_html       = state.get("patched_html_content", state.get("html_content", ""))
    html_source_path   = state.get("html_source_path", "unknown.html")
    ui_context         = state.get("ui_context", "General web UI")

    # ── Compute statistics ─────────────────────────────────────────────────
    sev_breakdown   = _compute_severity_breakdown(verified_issues)
    total_issues    = len(verified_issues)
    resolved_count  = sum(len(vr.issues_resolved)          for vr in verification_results)
    remaining_count = sum(len(vr.issues_remaining)         for vr in verification_results)
    regressions     = sum(len(vr.new_issues_introduced)    for vr in verification_results)
    completed_count = sum(1 for vr in verification_results if vr.task_completed_after_patch)

    # ── LLM executive summary ──────────────────────────────────────────────
    overall_score, executive_summary, top_recommendations = _generate_summary(
        total_issues=total_issues,
        issues_resolved=resolved_count,
        issues_remaining=remaining_count,
        completed=completed_count,
        total_personas=len(personas),
        severity_breakdown=sev_breakdown,
        clusters=issue_clusters,
    )

    # ── Assemble report ────────────────────────────────────────────────────
    report_id = f"report_{uuid.uuid4().hex[:8]}"

    # Ensure unified_patch_set exists (even if empty)
    if unified_patch_set is None:
        from schemas.patch_schema import UnifiedPatchSet
        unified_patch_set = UnifiedPatchSet(
            patches=[],
            conflicts_detected=0,
            conflicts_resolved=0,
        )

    # Ensure ui_analysis is never None — DiagnosticReport requires a valid object.
    # This happens on early short-circuits (pipeline_error, HTML not found, etc.)
    if ui_analysis is None:
        from schemas.persona_schema import UIAnalysis
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

    # ── Persist ────────────────────────────────────────────────────────────
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
) -> tuple[float, str, list[str]]:
    """
    Call the supervisor LLM to produce overall_score, executive_summary,
    and top_recommendations.  Falls back to deterministic values on failure.
    """
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
        total_issues=total_issues,
        issues_resolved=issues_resolved,
        issues_remaining=issues_remaining,
        completed=completed,
        total_personas=total_personas,
        severity_breakdown=sev_str,
        clusters_summary=clusters_summary or "No clusters found.",
    )

    raw, error = _call_supervisor_llm(
        system=REPORT_SUMMARY_SYSTEM,
        user=user,
        task="report_summary",
    )

    if error:
        logger.warning("report_generator.llm_error", error=error)
        return _fallback_summary(total_issues, issues_remaining, severity_breakdown)

    try:
        data = json.loads(raw)
        score = float(data.get("overall_score", 5.0))
        score = max(0.0, min(10.0, score))
        summary = data.get("executive_summary", "")
        recs    = data.get("top_recommendations", [])
        if not isinstance(recs, list):
            recs = [str(recs)]
        return score, summary, recs[:5]
    except Exception as e:
        logger.warning("report_generator.parse_error", error=str(e))
        return _fallback_summary(total_issues, issues_remaining, severity_breakdown)


def _fallback_summary(
    total_issues: int,
    issues_remaining: int,
    sev: SeverityBreakdown,
) -> tuple[float, str, list[str]]:
    """Deterministic fallback when LLM is unavailable."""
    if total_issues == 0:
        score = 9.0
        summary = (
            "No usability or accessibility issues were detected during simulation. "
            "All personas completed their tasks. The UI appears well-structured and "
            "accessible. Continue monitoring with updated personas as the UI evolves."
        )
        recs = ["No immediate actions required."]
    else:
        resolved_ratio = 1.0 - (issues_remaining / max(total_issues, 1))
        score = max(1.0, min(9.0, 4.0 + resolved_ratio * 5.0 - sev.critical * 1.5 - sev.high * 0.5))
        summary = (
            f"The UI evaluation found {total_issues} issues across all simulated personas. "
            f"{sev.critical} critical and {sev.high} high severity issues were identified. "
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
    """Write the DiagnosticReport as JSON to the output directory."""
    try:
        output_dir = Path(settings.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        out_path = output_dir / f"{report.report_id}.json"
        out_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
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
    """
    Uses the supervisor LLM for report summary generation.
    Rate-limiting handled by groq_chat_completion (semaphore + backoff).
    """
    return groq_chat_completion(
        api_key     = settings.supervisor_api_key,
        model       = settings.supervisor_llm_model,
        messages    = [{"role": "system", "content": system},
                       {"role": "user",   "content": user}],
        temperature = settings.supervisor_temperature,
        max_tokens  = getattr(settings, 'supervisor_max_tokens', settings.llm_max_output_tokens),
        task        = task,
    )