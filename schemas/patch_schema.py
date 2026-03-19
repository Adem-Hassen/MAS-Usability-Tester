from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class PatchType(str, Enum):
    # HTML fixes
    HTML_ATTRIBUTE    = "html_attribute"    # add/modify attribute: aria-label, alt, role, tabindex
    HTML_STRUCTURE    = "html_structure"    # add or restructure elements: wrap in <label>, add <legend>
    CONTENT           = "content"           # rewrite text: button label, error message, placeholder
    REMOVE_ELEMENT    = "remove_element"    # remove a broken or harmful element
    REORDER_ELEMENTS  = "reorder_elements"  # fix tab/reading order
    INLINE_STYLE      = "inline_style"      # add/fix style="" attribute directly on element

    # CSS fixes
    CSS_CLASS         = "css_class"         # add/modify a CSS class definition
    CSS_RULE          = "css_rule"          # add/override a standalone CSS rule block
                                            # use for: contrast, focus rings, spacing, visibility

    # JavaScript fixes
    JS_SNIPPET        = "js_snippet"        # inject a JS behaviour fix
                                            # use for: keyboard traps, focus management,
                                            # live region updates, dynamic announcements


class PatchProposal(BaseModel):
    patch_id:       str = Field(..., description="Unique ID, e.g. 'rec_cluster_2_abc123'")
    cluster_id:     str = Field(..., description="The IssueCluster this patch addresses")
    recommender_id: str = Field(..., description="ID of the Recommender Agent that produced this")

    patch_type:         PatchType
    severity_addressed: str = Field(..., description="The dominant severity level being fixed")

    target_element: str = Field(..., description="CSS selector of the element to modify")
    description:    str = Field(..., description="Human-readable explanation of what this patch does")

    before_snippet: str = Field(..., description="Original HTML/CSS/JS snippet (copy exactly from source)")
    after_snippet:  str = Field(..., description="Proposed fixed HTML/CSS/JS snippet")

    css_snippet: Optional[str] = Field(
        None,
        description="Standalone CSS rule(s) to inject when patch_type is css_rule or css_class"
    )
    js_snippet: Optional[str] = Field(
        None,
        description="Standalone JS block to inject before </body> when patch_type is js_snippet"
    )

    confidence:    float = Field(..., ge=0.0, le=1.0)
    wcag_reference: Optional[str] = None
    rationale:     str = Field(..., description="Why this fix was chosen over alternatives")
    side_effects:  list[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}


class ConflictRecord(BaseModel):
    conflict_id:          str
    patch_id_a:           str
    patch_id_b:           str
    target_element:       str
    conflict_description: str
    conflict_severity:    str


class NegotiationRound(BaseModel):
    round_number:        int
    conflict_id:         str
    agent_a_argument:    str
    agent_b_argument:    str
    mediator_assessment: str
    resolution_reached:  bool = False
    proposed_resolution: Optional[str] = None


class NegotiationSession(BaseModel):
    session_id:       str
    conflict:         ConflictRecord
    rounds:           list[NegotiationRound]
    final_resolution: str
    winning_patch_id: Optional[str] = None
    merged_snippet:   Optional[str] = None


class ResolvedPatch(BaseModel):
    resolved_patch_id:    str
    source_patch_ids:     list[str]
    cluster_ids:          list[str]
    patch_type:           PatchType
    target_element:       str
    description:          str
    before_snippet:       str
    after_snippet:        str
    css_snippet:          Optional[str] = None
    js_snippet:           Optional[str] = None
    negotiation_rounds:   int = 0
    resolution_rationale: str
    wcag_reference:       Optional[str] = None
    confidence:           float = Field(..., ge=0.0, le=1.0)

    model_config = {"use_enum_values": True}


class UnifiedPatchSet(BaseModel):
    patches:              list[ResolvedPatch]
    conflicts_detected:   int
    conflicts_resolved:   int
    negotiation_sessions: list[NegotiationSession] = Field(default_factory=list)
    unresolved_conflicts: list[ConflictRecord]      = Field(default_factory=list)