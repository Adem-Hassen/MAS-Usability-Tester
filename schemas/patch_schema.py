from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum




class PatchType(str, Enum):
    HTML_ATTRIBUTE    = "html_attribute"    # add/modify attribute: aria-label, alt, role, etc.
    HTML_STRUCTURE    = "html_structure"    # add or restructure elements: wrap in <label>, add <legend>
    CSS_CLASS         = "css_class"         # add/modify CSS for focus styles, contrast, visibility
    CONTENT           = "content"           # rewrite text: button label, error message, placeholder
    REMOVE_ELEMENT    = "remove_element"    # remove a broken or harmful element
    REORDER_ELEMENTS  = "reorder_elements"  # fix tab/reading order


# ---------------------------------------------------------------------------
# Patch proposal (from a single Recommender Agent)
# ---------------------------------------------------------------------------

class PatchProposal(BaseModel):
    """
    A single fix proposed by a Recommender Agent for one IssueCluster.
    Multiple proposals may exist for the same element → conflict detection needed.
    """
    patch_id: str = Field(..., description="Unique ID, e.g. 'rec_cluster_2_abc123'")
    cluster_id: str = Field(..., description="The IssueCluster this patch addresses")
    recommender_id: str = Field(..., description="ID of the Recommender Agent that produced this")

    # Classification
    patch_type: PatchType
    severity_addressed: str = Field(..., description="The dominant severity level being fixed")

    # The fix itself
    target_element: str = Field(..., description="CSS selector of the element to modify")
    description: str = Field(
        ...,
        description="Human-readable explanation of what this patch does and why it resolves the issue"
    )
    before_snippet: str = Field(..., description="Original HTML snippet (for diff display)")
    after_snippet: str = Field(..., description="Proposed fixed HTML snippet")

    # Supporting info
    confidence: float = Field(..., ge=0.0, le=1.0, description="Agent's confidence in this fix")
    wcag_reference: Optional[str] = Field(
        None,
        description="WCAG criterion this fix satisfies, e.g. 'WCAG 2.1 SC 4.1.2'"
    )
    rationale: str = Field(
        ...,
        description="Why this specific fix was chosen over alternatives"
    )
    side_effects: list[str] = Field(
        default_factory=list,
        description="Potential unintended consequences of this patch"
    )

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Conflict detection and LLM negotiation
# ---------------------------------------------------------------------------

class ConflictRecord(BaseModel):
    """A detected conflict between two patch proposals targeting the same element."""
    conflict_id: str
    patch_id_a: str
    patch_id_b: str
    target_element: str = Field(..., description="The element both patches touch")
    conflict_description: str = Field(
        ...,
        description="Why these two patches conflict: overlapping attributes, contradictory structure, etc."
    )
    conflict_severity: str = Field(
        ...,
        description="low | medium | high — how incompatible the patches are"
    )


class NegotiationRound(BaseModel):
    """A single round of LLM-based debate between two recommender agents."""
    round_number: int
    conflict_id: str
    agent_a_argument: str = Field(..., description="Agent A's argument for why its patch should win")
    agent_b_argument: str = Field(..., description="Agent B's argument for why its patch should win")
    mediator_assessment: str = Field(
        ...,
        description="Mediator LLM's assessment after hearing both arguments"
    )
    resolution_reached: bool = Field(False, description="Whether this round produced a resolution")
    proposed_resolution: Optional[str] = Field(
        None,
        description="The mediator's proposed resolution if resolution_reached is True"
    )


class NegotiationSession(BaseModel):
    """
    Full negotiation session for one conflict.
    Contains all rounds until resolution or exhaustion.
    """
    session_id: str
    conflict: ConflictRecord
    rounds: list[NegotiationRound]
    final_resolution: str = Field(
        ...,
        description="chose_a | chose_b | merged | unresolved"
    )
    winning_patch_id: Optional[str] = Field(
        None,
        description="The patch_id that won (None if merged or unresolved)"
    )
    merged_snippet: Optional[str] = Field(
        None,
        description="If resolution = 'merged': the combined after_snippet"
    )


# ---------------------------------------------------------------------------
# Resolved patch and unified set
# ---------------------------------------------------------------------------

class ResolvedPatch(BaseModel):
    """
    Final unified patch after conflict resolution.
    Applied to the HTML by the patch applicator node.
    """
    resolved_patch_id: str
    source_patch_ids: list[str] = Field(..., description="Original patch IDs that were merged/selected")
    cluster_ids: list[str] = Field(..., description="Issue cluster IDs this patch resolves")
    patch_type: PatchType
    target_element: str
    description: str
    before_snippet: str
    after_snippet: str
    negotiation_rounds: int = Field(0, description="Number of negotiation rounds needed (0 = no conflict)")
    resolution_rationale: str = Field(
        ...,
        description="Why this resolution was chosen — especially important for merged patches"
    )
    wcag_reference: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)

    model_config = {"use_enum_values": True}


class UnifiedPatchSet(BaseModel):
    """
    Complete set of resolved patches ready for application and verification.
    Final output of the Conflict Resolver Node.
    """
    patches: list[ResolvedPatch]
    conflicts_detected: int
    conflicts_resolved: int
    negotiation_sessions: list[NegotiationSession] = Field(
        default_factory=list,
        description="Full negotiation history for auditability"
    )
    unresolved_conflicts: list[ConflictRecord] = Field(
        default_factory=list,
        description="Conflicts that could not be resolved (should be empty)"
    )