#schemas/report_schemas.py

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from schemas.persona_schema import UIAnalysis, PersonaProfile
from schemas.issue_schema import IssueCluster, PersonaSimulationResult, IssueSeverity
from schemas.patch_schema import UnifiedPatchSet


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

class VerificationResult(BaseModel):
    """Result of re-running persona simulations on the patched HTML."""
    persona_id: str
    persona_name: str
    issues_before: list[str] = Field(..., description="issue_ids present before patching")
    issues_remaining: list[str] = Field(..., description="issue_ids still present after patching")
    issues_resolved: list[str] = Field(..., description="issue_ids successfully fixed")
    new_issues_introduced: list[str] = Field(
        default_factory=list,
        description="issue_ids of regressions introduced by the patches"
    )
    task_completed_after_patch: bool
    fully_resolved: bool = Field(
        ...,
        description="True if all critical and high severity issues for this persona are resolved"
    )


# ---------------------------------------------------------------------------
# Severity breakdown (for summary stats)
# ---------------------------------------------------------------------------

class SeverityBreakdown(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


# ---------------------------------------------------------------------------
# Diagnostic report
# ---------------------------------------------------------------------------

class DiagnosticReport(BaseModel):
    """
    Final output of the full UI evaluation pipeline.
    Written as JSON to the output directory.
    """
    report_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    html_source_path: str
    ui_context: str
    correction_loop_count: int

    # Analysis
    ui_analysis: UIAnalysis

    # Personas
    personas: list[PersonaProfile]
    persona_results: list[PersonaSimulationResult]

    # Issues
    issue_clusters: list[IssueCluster]
    total_issues_found: int
    severity_breakdown: SeverityBreakdown

    # Patches
    unified_patch_set: UnifiedPatchSet
    total_patches_applied: int

    # Verification
    verification_results: list[VerificationResult]
    issues_resolved_count: int
    issues_remaining_count: int
    regressions_introduced: int
    verification_passed: bool

    # Summary
    overall_score: float = Field(
        ..., ge=0.0, le=10.0,
        description="Overall UI quality score: 10 = perfect, 0 = completely broken"
    )
    executive_summary: str = Field(
        ...,
        description="2-3 paragraph human-readable summary for a developer or designer"
    )
    top_recommendations: list[str] = Field(
        ...,
        description="Top 5 prioritized actionable improvements, ordered by impact"
    )
    

    model_config = {"use_enum_values": True}