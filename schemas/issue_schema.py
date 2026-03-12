# schemas/issue_schema.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class IssueSeverity(str, Enum):
    CRITICAL = "critical"   # blocks task completion entirely
    HIGH     = "high"       # major friction, likely causes task abandonment
    MEDIUM   = "medium"     # noticeable issue, workaround possible
    LOW      = "low"        # minor annoyance, cosmetic


class IssueCategory(str, Enum):
    USABILITY     = "usability"      # general usability friction
    ACCESSIBILITY = "accessibility"  # WCAG / a11y violations
    NAVIGATION    = "navigation"     # wayfinding, back-tracking, dead ends
    CLARITY       = "clarity"        # confusing labels, missing feedback, ambiguous copy
    FORM          = "form"           # validation, input errors, submission flow
    OTHER         = "other"


class StopReason(str, Enum):
    GOAL_ACHIEVED    = "goal_achieved"     # task successfully completed
    DEAD_END         = "dead_end"          # no valid next action found
    MAX_STEPS        = "max_steps"         # hit settings.persona_max_steps
    REPEATED_ACTION  = "repeated_action"  # same (action, selector) seen twice → loop guard


ActionType = Literal["click", "type", "scroll", "navigate", "observe", "hover"]


# ---------------------------------------------------------------------------
# Action trace
# ---------------------------------------------------------------------------

class ActionStep(BaseModel):
    """One step in a persona's interaction trace."""
    step_number: int
    action_type: ActionType
    target_selector: Optional[str] = Field(
        None,
        description="CSS selector of the target element (None for page-level actions)"
    )
    target_description: str = Field("", description="Human-readable description of the target")
    value: Optional[str] = Field(None, description="Text typed, scroll direction, URL navigated to, etc.")
    reasoning: str = Field(
        "",
        description="Why the agent chose this action given the persona profile and current goal"
    )
    page_state_summary: str = Field(
        "",
        description="Brief description of the visible page state before this action"
    )
    success: bool = Field(True, description="Whether the action executed without error")
    error_message: Optional[str] = None
    issue_triggered: Optional[str] = Field(
        None,
        description="issue_id if this step directly revealed an issue"
    )


# ---------------------------------------------------------------------------
# Issue report
# ---------------------------------------------------------------------------

class IssueReport(BaseModel):
    """
    A single usability or accessibility issue found during a persona simulation.
    Produced by the Persona Agent, consumed by the Clustering Node.
    """
    issue_id: str = Field(..., description="Unique ID, e.g. 'persona_1_issue_3'")
    persona_id: str
    persona_name: str

    # Classification
    severity: IssueSeverity
    category: IssueCategory
    wcag_criterion: Optional[str] = Field(
        None,
        description="Relevant WCAG 2.1/2.2 criterion if applicable, e.g. '1.1.1 Non-text Content'"
    )

    # Description
    title: str = Field(..., description="Short title, e.g. 'Submit button has no accessible name'")
    description: str = Field(
        ...,
        description="Detailed explanation of what went wrong and why it matters for this persona"
    )
    affected_element: Optional[str] = Field(
        None,
        description="CSS selector of the element causing the issue"
    )
    affected_element_html: Optional[str] = Field(
        None,
        description="The raw HTML of the problematic element (snippet)"
    )
    step_number: int = Field(..., description="Step in the action trace where this issue was encountered")

    # Evidence
    page_context: str = Field(
        ...,
        description="What was visible/happening on the page when the issue occurred"
    )
    reproduction_steps: list[str] = Field(
        ...,
        description="Minimal ordered steps to reproduce the issue"
    )
    persona_impact: str = Field(
        ...,
        description="How this issue specifically affected this persona's ability to complete their goal"
    )

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Simulation result
# ---------------------------------------------------------------------------

class PersonaSimulationResult(BaseModel):
    """
    Full output of a single Persona Agent's simulation run.
    Collected by the graph after parallel execution.
    """
    persona_id: str
    persona_name: str
    task_goal: str
    selection_rationale: str = Field(
        "",
        description="Supervisor's reasoning for generating this persona — which risk it covers"
    )

    # Execution metadata
    stop_reason: StopReason
    steps_taken: int
    action_trace: list[ActionStep]

    # Findings
    issues: list[IssueReport]
    task_completed: bool
    completion_confidence: float = Field(
        0.0, ge=0.0, le=1.0,
        description="0 = definitely failed, 1 = definitely completed"
    )

    # Summary
    overall_experience: str = Field(
        ...,
        description="Free-text narrative of the persona's full experience — what worked, what didn't"
    )
    blocker_summary: Optional[str] = Field(
        None,
        description="If task not completed: description of the main blocker"
    )

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Issue cluster
# ---------------------------------------------------------------------------

class IssueCluster(BaseModel):
    """
    A group of semantically related issues produced by the Clustering Node.
    One IssueCluster → one Recommender Agent instance.
    """
    cluster_id: str
    cluster_label: str = Field(..., description="Short human-readable label, e.g. 'Missing form labels'")
    issues: list[IssueReport]

    # Dominant characteristics (computed from member issues)
    dominant_category: IssueCategory
    dominant_severity: IssueSeverity
    affected_personas: list[str] = Field(
        ...,
        description="persona_ids of all personas that encountered issues in this cluster"
    )
    affected_elements: list[str] = Field(
        default_factory=list,
        description="Deduplicated CSS selectors of all elements involved across all issues in cluster"
    )
    representative_description: str = Field(
        ...,
        description="2-3 sentence summary of what all issues in this cluster have in common"
    )
    issue_count: int = Field(..., description="Number of issues in this cluster")

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Trace verification
# ---------------------------------------------------------------------------

class TraceVerdict(str, Enum):
    VALID    = "valid"     # action and result are consistent and plausible
    SUSPECT  = "suspect"   # action plausible but result inconsistent or exaggerated
    INVALID  = "invalid"   # action was hallucinated, impossible, or never executed


class StepVerification(BaseModel):
    """Supervisor's verdict on a single action step."""
    step_number: int
    verdict: TraceVerdict
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str = Field(..., description="Why this verdict was assigned")
    flagged_issue_ids: list[str] = Field(
        default_factory=list,
        description="issue_ids that should be discarded if this step is invalid/suspect"
    )

    model_config = {"use_enum_values": True}


class TraceVerification(BaseModel):
    """Full trace-integrity verdict for one persona's simulation."""
    persona_id: str
    persona_name: str
    overall_verdict: TraceVerdict
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    step_verifications: list[StepVerification]
    discarded_issue_ids: list[str] = Field(
        default_factory=list,
        description="issue_ids removed from consideration due to invalid/suspect steps"
    )
    summary: str = Field(..., description="1-2 sentence summary of trace quality")

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Recommender agent profile
# ---------------------------------------------------------------------------

class RecommenderFocus(str, Enum):
    ACCESSIBILITY = "accessibility"
    USABILITY     = "usability"
    NAVIGATION    = "navigation"
    FORM          = "form"
    CLARITY       = "clarity"
    MIXED         = "mixed"


class RecommenderProfile(BaseModel):
    """
    Profile for a single Recommender Agent, generated by the supervisor
    after clustering. One profile → one recommender instance spawned.
    """
    recommender_id: str = Field(..., description="e.g. 'rec_1'")
    cluster_id: str = Field(..., description="The IssueCluster this agent owns")
    cluster_label: str = Field(..., description="Human-readable cluster label")
    focus: RecommenderFocus = Field(..., description="Primary domain expertise for this agent")

    # What the recommender needs to know
    cluster_summary: str = Field(
        ..., description="2-3 sentence brief of the cluster's issues for the recommender"
    )
    dominant_severity: str = Field(..., description="critical | high | medium | low")
    affected_elements: list[str] = Field(
        default_factory=list,
        description="CSS selectors of elements the recommender should target"
    )
    wcag_references: list[str] = Field(
        default_factory=list,
        description="Relevant WCAG criteria the recommender should satisfy"
    )

    # Instruction and constraints
    fix_strategy_hint: str = Field(
        ...,
        description=(
            "Supervisor's guidance on the recommended fix approach: "
            "what type of change (attribute / structure / content / CSS) "
            "and what constraints to respect (no JS changes, preserve layout, etc.)"
        )
    )
    priority: int = Field(
        ..., ge=1,
        description="1 = highest priority (fix first). Based on severity and persona impact breadth."
    )

    model_config = {"use_enum_values": True}