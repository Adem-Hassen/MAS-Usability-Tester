from __future__ import annotations

import json
import uuid
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from core.state import GraphState
from schemas.issue_schema import IssueCluster, RecommenderProfile, IssueReport
from schemas.patch_schema import PatchProposal, PatchType
from prompts.recommender_prompts import (
    RECOMMENDER_SYSTEM,
    RECOMMENDER_USER,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def recommender_node(state: GraphState) -> dict:
    """
    LangGraph node. Receives state with 'current_recommender_profile' injected
    by Send() fan-out (one per RecommenderProfile).

    Returns partial state update:
      - patch_proposals: [PatchProposal]   — appended via operator.add
      - swarm_claims:    [dict]             — appended via operator.add
    """
    profile: RecommenderProfile = state["current_recommender_profile"]
    logger.info(
        "recommender.start",
        recommender_id=profile.recommender_id,
        recommender_name=profile.recommender_name,
        cluster_id=profile.cluster_id,
        focus=profile.focus,
        priority=profile.priority,
    )

    cluster = _find_cluster(state, profile.cluster_id)
    if cluster is None:
        logger.error("recommender.cluster_not_found",
                     recommender_id=profile.recommender_id,
                     cluster_id=profile.cluster_id)
        return {"patch_proposals": [], "swarm_claims": []}

    peer_claims: list[dict] = state.get("swarm_claims") or []
    overlapping_selectors = _find_overlapping_selectors(profile, peer_claims)
    if overlapping_selectors:
        logger.info("recommender.swarm_overlap_detected",
                    recommender_id=profile.recommender_id,
                    overlapping=overlapping_selectors)

    html_content = state.get("html_content", "")
    ui_context   = state.get("ui_context", "General web UI")

    proposal = _propose_patch(profile, cluster, html_content, ui_context, overlapping_selectors)

    if proposal is None:
        logger.warning("recommender.proposal_failed",
                       recommender_id=profile.recommender_id,
                       cluster_id=profile.cluster_id)
        proposal = _fallback_proposal(profile, cluster)

    logger.info(
        "recommender.proposal_complete",
        recommender_id=profile.recommender_id,
        patch_id=proposal.patch_id,
        patch_type=proposal.patch_type,
        target=proposal.target_element,
        confidence=proposal.confidence,
        has_css=bool(proposal.css_snippet),
        has_js=bool(proposal.js_snippet),
    )

    claim = {
        "selector":       proposal.target_element,
        "recommender_id": profile.recommender_id,
        "cluster_id":     profile.cluster_id,
        "patch_type":     str(proposal.patch_type),
    }

    return {
        "patch_proposals": [proposal],
        "swarm_claims":    [claim],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_cluster(state: GraphState, cluster_id: str) -> Optional[IssueCluster]:
    for c in state.get("issue_clusters", []):
        if c.cluster_id == cluster_id:
            return c
    return None


def _find_overlapping_selectors(
    profile: RecommenderProfile,
    peer_claims: list[dict],
) -> list[str]:
    my_selectors = set(profile.affected_elements)
    return list({
        claim.get("selector", "")
        for claim in peer_claims
        if claim.get("selector", "") in my_selectors
    } - {""})


def _format_issues_detail(issues: list[IssueReport]) -> str:
    lines = []
    for i, iss in enumerate(issues, 1):
        lines.append(f"Issue {i} (id={iss.issue_id}, severity={iss.severity}):")
        lines.append(f"  Title: {iss.title}")
        lines.append(f"  Description: {iss.description}")
        if iss.affected_element:
            lines.append(f"  Affected selector: {iss.affected_element}")
        if iss.affected_element_html:
            lines.append(f"  Element HTML: {iss.affected_element_html[:300]}")
        if iss.wcag_criterion:
            lines.append(f"  WCAG: {iss.wcag_criterion}")
        if iss.reproduction_steps:
            lines.append(f"  Repro: {' -> '.join(iss.reproduction_steps)}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PatchType normalisation
# Maps every alias the LLM might produce to a valid PatchType enum value
# ---------------------------------------------------------------------------

_PATCH_TYPE_ALIASES: dict[str, str] = {
    # CSS
    "css":              "css_rule",
    "css_rule":         "css_rule",
    "css_class":        "css_class",
    "style":            "css_rule",
    "stylesheet":       "css_rule",
    "styling":          "css_rule",
    "visual":           "css_rule",
    "contrast":         "css_rule",
    "focus":            "css_rule",
    # JS
    "js":               "js_snippet",
    "js_snippet":       "js_snippet",
    "javascript":       "js_snippet",
    "script":           "js_snippet",
    "behavior":         "js_snippet",
    "behaviour":        "js_snippet",
    "keyboard":         "js_snippet",
    # HTML
    "html_attribute":   "html_attribute",
    "attribute":        "html_attribute",
    "html_structure":   "html_structure",
    "structure":        "html_structure",
    "html_element":     "html_structure",
    "element":          "html_structure",
    "content":          "content",
    "text":             "content",
    "remove_element":   "remove_element",
    "remove":           "remove_element",
    "reorder_elements": "reorder_elements",
    "reorder":          "reorder_elements",
    "inline_style":     "inline_style",
    "inline":           "inline_style",
}


def _normalise_patch_type(raw: str) -> str:
    """Map any LLM-produced patch_type string to a valid PatchType enum value."""
    normalised = _PATCH_TYPE_ALIASES.get(str(raw).lower().strip())
    if normalised:
        return normalised
    try:
        PatchType(raw)
        return raw
    except ValueError:
        return "html_attribute"


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------

def _propose_patch(
    profile: RecommenderProfile,
    cluster: IssueCluster,
    html_content: str,
    ui_context: str,
    overlapping_selectors: list[str],
) -> Optional[PatchProposal]:

    system = RECOMMENDER_SYSTEM.format(
        cluster_id=profile.cluster_id,
        recommender_id=profile.recommender_id,
    )

    overlap_note = ""
    if overlapping_selectors:
        overlap_note = (
            f"\n\nWARNING — SWARM OVERLAP: The following selectors are also targeted "
            f"by peer agents: {overlapping_selectors}. "
            f"Note overlaps in 'side_effects'. Use a non-overlapping approach if possible."
        )

    html_snippet = _extract_relevant_html(html_content, profile.affected_elements)

    user = RECOMMENDER_USER.format(
        cluster_id=profile.cluster_id,
        cluster_label=profile.cluster_label,
        dominant_severity=profile.dominant_severity,
        dominant_category=str(cluster.dominant_category),
        affected_elements=", ".join(profile.affected_elements) or "see individual issues",
        representative_description=profile.cluster_summary,
        issues_detail=_format_issues_detail(cluster.issues),
        html_content=html_snippet,
        ui_context=ui_context,
    ) + overlap_note

    raw, error = _call_recommender_llm(system, user, task="propose_patch")
    if error:
        logger.error("recommender.llm_error",
                     recommender_id=profile.recommender_id, error=error)
        return None

    try:
        data = json.loads(raw)

        # Unwrap single-key container {"proposal": {...}}
        if isinstance(data, dict) and len(data) == 1:
            val = next(iter(data.values()))
            if isinstance(val, dict) and "patch_id" in val:
                data = val

        # Ensure all required fields have defaults
        if not data.get("patch_id"):
            data["patch_id"] = f"{profile.recommender_id}_{profile.cluster_id}_{uuid.uuid4().hex[:6]}"
        if not data.get("cluster_id"):
            data["cluster_id"] = profile.cluster_id
        if not data.get("recommender_id"):
            data["recommender_id"] = profile.recommender_id
        if not data.get("severity_addressed"):
            data["severity_addressed"] = profile.dominant_severity
        if not data.get("before_snippet"):
            data["before_snippet"] = ""
        if not data.get("after_snippet"):
            data["after_snippet"] = ""
        if not data.get("rationale"):
            data["rationale"] = data.get("description", "No rationale provided")
        if "confidence" not in data:
            data["confidence"] = 0.5

        # Normalise patch_type — handles all LLM aliases for new CSS/JS types
        data["patch_type"] = _normalise_patch_type(data.get("patch_type", "html_attribute"))

        # Auto-populate css_snippet / js_snippet if LLM put content in after_snippet
        if data["patch_type"] in ("css_rule", "css_class") and not data.get("css_snippet"):
            data["css_snippet"] = data.get("after_snippet", "")

        if data["patch_type"] == "js_snippet" and not data.get("js_snippet"):
            data["js_snippet"] = data.get("after_snippet", "")

        return PatchProposal(**data)

    except Exception as e:
        logger.error("recommender.proposal_parse_error",
                     recommender_id=profile.recommender_id,
                     error=str(e), raw=raw[:500])
        return None


def _fallback_proposal(
    profile: RecommenderProfile,
    cluster: IssueCluster,
) -> PatchProposal:
    """Minimal safe proposal returned when the LLM call fails entirely."""
    return PatchProposal(
        patch_id=f"{profile.recommender_id}_{profile.cluster_id}_fallback",
        cluster_id=profile.cluster_id,
        recommender_id=profile.recommender_id,
        patch_type=PatchType.HTML_ATTRIBUTE,
        severity_addressed=profile.dominant_severity,
        target_element=(profile.affected_elements[0] if profile.affected_elements else "body"),
        description=f"Fallback patch for cluster {profile.cluster_id} — LLM call failed",
        before_snippet="",
        after_snippet="",
        confidence=0.0,
        rationale="Fallback — LLM call failed. Manual review required.",
        side_effects=["Placeholder patch — applies no changes."],
    )


def _extract_relevant_html(html_content: str, affected_elements: list[str]) -> str:
    MAX_CHARS = 8_000
    if len(html_content) <= MAX_CHARS:
        return html_content
    if affected_elements:
        target = affected_elements[0].lstrip("#.").split("[")[0]
        idx = html_content.find(target)
        if idx != -1:
            start = max(0, idx - 2_000)
            end   = min(len(html_content), idx + 6_000)
            return html_content[start:end]
    return html_content[:MAX_CHARS]


def _call_recommender_llm(
    system: str,
    user:   str,
    task:   str,
) -> tuple[str, Optional[str]]:
    return groq_chat_completion(
        api_key     = settings.recommender_api_key,
        model       = settings.recommender_llm_model,
        messages    = [{"role": "system", "content": system},
                       {"role": "user",   "content": user}],
        temperature = settings.recommender_temperature,
        max_tokens  = getattr(settings, 'recommender_max_tokens', settings.llm_max_output_tokens),
        task        = task,
    )