# core/state.py
from typing import TypedDict, Optional, Annotated
import operator
from schemas.persona_schema import UIAnalysis, PersonaProfile
from schemas.issue_schema import PersonaSimulationResult, IssueCluster
from schemas.patch_schema import PatchProposal, UnifiedPatchSet
from schemas.report_schema import VerificationResult, DiagnosticReport


class GraphState(TypedDict):
    """
    The shared state passed between all LangGraph nodes.
    Each node reads from and writes to this state.

    Annotated with operator.add on list fields so that
    parallel nodes (e.g. persona agents) can append results
    without overwriting each other.
    """

    # --- Input ---
    html_source_path: str           # absolute path to the HTML file
    html_content: str               # raw HTML string read from file
    ui_context: str                 # user-provided description of the UI's purpose
    # Storage values to seed into the browser before page load (prevents auth-guard redirects).
    # Detected automatically by the supervisor from the HTML source.
    # Format: {"localStorage": {"key": "value"}, "sessionStorage": {"key": "value"}}
    storage_seed: Optional[dict]    # e.g. {"localStorage": {"userEmail": "test@test.com"}}

    # --- Supervisor outputs ---
    ui_analysis: Optional[UIAnalysis]       # structured analysis of the HTML
    personas: list[PersonaProfile]          # generated persona profiles

    # --- Persona agent outputs (parallel fan-out, results accumulated) ---
    simulation_results: Annotated[list[PersonaSimulationResult], operator.add]

    # --- Post-simulation analysis (supervisor phase 2) ---
    trace_verifications: list   # list[TraceVerification] — one per persona
    verified_results: list      # list[PersonaSimulationResult] — INVALID traces removed, INVALID steps stripped
    verified_issues: list       # list[IssueReport] — issues from valid/suspect steps only
    issue_clusters: list        # list[IssueCluster] — clustered verified issues
    recommender_profiles: list  # list[RecommenderProfile] — one per cluster

    # --- Recommender outputs (parallel fan-out, one per cluster) ---
    patch_proposals: Annotated[list[PatchProposal], operator.add]

    # --- Conflict resolver output ---
    unified_patch_set: Optional[UnifiedPatchSet]

    # --- Verification ---
    patched_html_content: Optional[str]     # HTML after patches applied
    verification_results: list[VerificationResult]
    correction_loop_count: int              # how many times we've looped back

    # --- Final output ---
    report: Optional[DiagnosticReport]

    # --- Control flags ---
    verification_passed: bool               # True = move to report, False = loop back
    pipeline_error: Optional[str]           # set if any node hits an unrecoverable error