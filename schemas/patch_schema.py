# schemas/patch_schema.py

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class PatchType(str, Enum):
    HTML_ATTRIBUTE    = "html_attribute"
    HTML_STRUCTURE    = "html_structure"
    CONTENT           = "content"
    REMOVE_ELEMENT    = "remove_element"
    REORDER_ELEMENTS  = "reorder_elements"
    INLINE_STYLE      = "inline_style"
    CSS_CLASS         = "css_class"
    CSS_RULE          = "css_rule"
    JS_SNIPPET        = "js_snippet"


class PatchProposal(BaseModel):
    patch_id:       str = Field(..., description="Unique ID, e.g. 'rec_cluster_2_abc123'")
    cluster_id:     str = Field(..., description="The IssueCluster this patch addresses")
    recommender_id: str = Field(..., description="ID of the Recommender Agent that produced this")

    patch_type:         PatchType
    severity_addressed: str = Field(..., description="The dominant severity level being fixed")

    target_element: str = Field(default="", description="CSS selector of the element to modify")
    description:    str = Field(default="", description="Human-readable explanation of what this patch does")

    # For HTML patches: before/after contain the HTML snippets being swapped.
    # For CSS/JS patches: these are empty string or null — the payload is in
    # css_snippet / js_snippet instead.
    before_snippet: Optional[str] = Field(
        default="",
        description="Original HTML snippet (for HTML patches) or '' for CSS/JS patches"
    )
    after_snippet: Optional[str] = Field(
        default="",
        description="Fixed HTML snippet (for HTML patches) or null for CSS/JS patches"
    )

    css_snippet: Optional[str] = Field(
        None,
        description="Standalone CSS rule(s) to inject — required when patch_type is css_rule or css_class"
    )
    js_snippet: Optional[str] = Field(
        None,
        description="Standalone JS block to inject before </body> — required when patch_type is js_snippet"
    )

    confidence:     float = Field(default=0.5, ge=0.0, le=1.0)
    wcag_reference: Optional[str] = None
    rationale:      str = Field(default="", description="Why this fix was chosen over alternatives")
    side_effects:   list[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}


class ConflictRecord(BaseModel):
    conflict_id:          str
    patch_id_a:           str
    patch_id_b:           str
    target_element:       str = ""
    conflict_description: str = ""
    conflict_severity:    str = "medium"


class NegotiationRound(BaseModel):
    round_number:        int
    conflict_id:         str
    agent_a_argument:    str = ""
    agent_b_argument:    str = ""
    mediator_assessment: str = ""
    resolution_reached:  bool = False
    proposed_resolution: Optional[str] = None


class NegotiationSession(BaseModel):
    session_id:       str
    conflict:         ConflictRecord
    rounds:           list[NegotiationRound] = Field(default_factory=list)
    final_resolution: str = "unresolved"
    winning_patch_id: Optional[str] = None
    merged_snippet:   Optional[str] = None


class ResolvedPatch(BaseModel):
    resolved_patch_id:    str
    source_patch_ids:     list[str] = Field(default_factory=list)
    cluster_ids:          list[str] = Field(default_factory=list)
    patch_type:           PatchType
    target_element:       str = ""
    description:          str = ""
    before_snippet:       Optional[str] = Field(default="")
    after_snippet:        Optional[str] = Field(default="")
    css_snippet:          Optional[str] = None
    js_snippet:           Optional[str] = None
    negotiation_rounds:   int = 0
    resolution_rationale: str = ""
    wcag_reference:       Optional[str] = None
    confidence:           float = Field(default=0.5, ge=0.0, le=1.0)

    model_config = {"use_enum_values": True}


class UnifiedPatchSet(BaseModel):
    patches:              list[ResolvedPatch] = Field(default_factory=list)
    conflicts_detected:   int = 0
    conflicts_resolved:   int = 0
    negotiation_sessions: list[NegotiationSession] = Field(default_factory=list)
    unresolved_conflicts: list[ConflictRecord] = Field(default_factory=list)