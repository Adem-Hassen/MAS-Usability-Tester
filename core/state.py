#core/state.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Optional, TypedDict
import operator

from schemas.persona_schema import UIAnalysis
from schemas.patch_schema import UnifiedPatchSet
from schemas.report_schema import DiagnosticReport


# ---------------------------------------------------------------------------
# PageContext — carries everything for one HTML page end-to-end
# ---------------------------------------------------------------------------

@dataclass
class PageContext:
    """Self-contained state for one page through the entire pipeline."""

    # ── Inputs ────────────────────────────────────────────────────────────
    html_source_path: str = ""
    html_content:     str = ""
    ui_context:       str = "General web UI"
    storage_seed:     Optional[dict] = None

    # ── Supervisor outputs ────────────────────────────────────────────────
    ui_analysis: Optional[UIAnalysis] = None
    personas:    list = field(default_factory=list)  # list[PersonaProfile]

    # ── Simulation ────────────────────────────────────────────────────────
    simulation_results: list = field(default_factory=list)  # list[PersonaSimulationResult]

    # ── Post-simulation analysis ──────────────────────────────────────────
    trace_verifications: list = field(default_factory=list)
    verified_results:    list = field(default_factory=list)
    verified_issues:     list = field(default_factory=list)

    # ── Recommender cycle ─────────────────────────────────────────────────
    issue_clusters:       list = field(default_factory=list)
    recommender_profiles: list = field(default_factory=list)
    patch_proposals:      list = field(default_factory=list)
    swarm_claims:         list = field(default_factory=list)

    # ── Conflict resolution ───────────────────────────────────────────────
    unified_patch_set: Optional[UnifiedPatchSet] = None

    # ── Patch application ─────────────────────────────────────────────────
    patched_html_content:  Optional[str] = None
    total_patches_applied: int           = 0

    # ── Verification ──────────────────────────────────────────────────────
    verification_results: list = field(default_factory=list)
    verification_passed:  bool = False

    # ── Correction loop ───────────────────────────────────────────────────
    correction_loop_count: int = 0

    # ── Final output ──────────────────────────────────────────────────────
    report: Optional[DiagnosticReport] = None

    # ── Per-page error ────────────────────────────────────────────────────
    page_error: Optional[str] = None


# ---------------------------------------------------------------------------
# GraphState — top-level LangGraph state
# ---------------------------------------------------------------------------

class GraphState(TypedDict, total=False):
    """
    Top-level state.  Parallel-write safety:

    supervisor_node (single)
        writes: supervisor_output (plain — one writer)

    page_pipeline_node × N (parallel — one per page, injected via Send)
        reads:  current_page_context  (injected by Send, not in shared state)
        writes: page_contexts  (Annotated — safe for parallel appends)
                reports        (Annotated — safe for parallel appends)

    No node writes the same non-Annotated field from two parallel branches.
    """

    # ── User input ────────────────────────────────────────────────────────
    pages_input: list            # list[{"html_path": str, "ui_context": str}]

    # ── Supervisor output (written once by supervisor_node) ───────────────
    supervisor_output: Optional[dict]   # {"page_contexts": [...], "used_*": [...]}

    # ── Per-page context injected via Send (NOT in shared state) ─────────
    # current_page_context is passed as an extra key in Send() payloads.
    # It is read by page_pipeline_node but never written to shared state
    # by parallel branches — each branch writes only to the Annotated lists.
    current_page_context: Optional[object]   # PageContext

    # ── Parallel-safe accumulators ────────────────────────────────────────
    page_contexts: Annotated[list, operator.add]    # list[PageContext]  — completed pages
    reports:       Annotated[list, operator.add]    # list[DiagnosticReport]

    # ── Cross-page persona diversity ──────────────────────────────────────
    used_persona_names:       list
    used_persona_goals:       list
    used_persona_constraints: list

    # ── Control ───────────────────────────────────────────────────────────
    pipeline_error: Optional[str]


# ---------------------------------------------------------------------------
# Initial state factory
# ---------------------------------------------------------------------------

def make_initial_state(
    pages: list[dict],
    used_persona_names:       list | None = None,
    used_persona_goals:       list | None = None,
    used_persona_constraints: list | None = None,
) -> dict:
    """Build the starting GraphState dict for a pipeline run."""
    return {
        "pages_input":              pages,
        "supervisor_output":        None,
        "current_page_context":     None,
        "page_contexts":            [],
        "reports":                  [],
        "used_persona_names":       list(used_persona_names       or []),
        "used_persona_goals":       list(used_persona_goals       or []),
        "used_persona_constraints": list(used_persona_constraints or []),
        "pipeline_error":           None,
    }