# agents/recommender/recommender_agent.py

from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from config.settings import settings
from tools.rate_limiter import chat_completion
from tools.llm_router import get_recommender_router
from schemas.persona_schema import UIAnalysis

from schemas.issue_schema import IssueCluster, RecommenderProfile, IssueReport
from schemas.patch_schema import PatchProposal, PatchType
from prompts.recommender_prompts import (
    RECOMMENDER_SYSTEM,
    RECOMMENDER_USER,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)

# Patch types whose payload lives in css_snippet / js_snippet, NOT after_snippet
_CSS_TYPES = {"css_rule", "css_class"}
_JS_TYPES  = {"js_snippet"}
_HTML_TYPES = {
    "html_attribute", "html_structure", "content",
    "remove_element", "reorder_elements", "inline_style",
}


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def recommender_node(state: dict) -> dict:
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

    ui_analysis  = state.get("ui_analysis")
    html_content = state.get("html_content", "")
    ui_context   = state.get("ui_context", "General web UI")
    design_tokens = state.get("design_tokens", {})

    proposal = _propose_patch(profile, cluster, html_content, ui_context, ui_analysis, overlapping_selectors, design_tokens)

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

def _find_cluster(state: dict, cluster_id: str) -> Optional[IssueCluster]:
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
    """Format issue details, capping to avoid token explosion."""
    MAX_ISSUES = 5          # cap number of issues shown
    MAX_DESC_LEN = 200      # cap description length
    MAX_HTML_LEN = 150      # cap HTML snippet length
    lines = []
    for i, iss in enumerate(issues[:MAX_ISSUES], 1):
        desc = (iss.description or "")[:MAX_DESC_LEN]
        lines.append(f"Issue {i} (id={iss.issue_id}, severity={iss.severity}):")
        lines.append(f"  Title: {iss.title}")
        lines.append(f"  Description: {desc}")
        if iss.affected_element:
            lines.append(f"  Selector: {iss.affected_element}")
        if iss.affected_element_html:
            lines.append(f"  HTML: {iss.affected_element_html[:MAX_HTML_LEN]}")
        if iss.wcag_criterion:
            lines.append(f"  WCAG: {iss.wcag_criterion}")
        lines.append("")
    if len(issues) > MAX_ISSUES:
        lines.append(f"... and {len(issues) - MAX_ISSUES} more issues (truncated)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PatchType normalisation
# ---------------------------------------------------------------------------

_PATCH_TYPE_ALIASES: dict[str, str] = {
    "css": "css_rule", "css_rule": "css_rule", "css_class": "css_class",
    "style": "css_rule", "stylesheet": "css_rule", "styling": "css_rule",
    "visual": "css_rule", "contrast": "css_rule", "focus": "css_rule",
    "js": "js_snippet", "js_snippet": "js_snippet", "javascript": "js_snippet",
    "script": "js_snippet", "behavior": "js_snippet", "behaviour": "js_snippet",
    "keyboard": "js_snippet", "dynamic": "js_snippet",
    "html_attribute": "html_attribute", "attribute": "html_attribute",
    "html_structure": "html_structure", "structure": "html_structure",
    "html_element": "html_structure", "element": "html_structure",
    "content": "content", "text": "content",
    "remove_element": "remove_element", "remove": "remove_element",
    "reorder_elements": "reorder_elements", "reorder": "reorder_elements",
    "inline_style": "inline_style", "inline": "inline_style",
}


def _normalise_patch_type(raw: str) -> str:
    normalised = _PATCH_TYPE_ALIASES.get(str(raw).lower().strip())
    if normalised:
        return normalised
    try:
        PatchType(raw)
        return raw
    except ValueError:
        return "html_attribute"


# ---------------------------------------------------------------------------
# Snippet validation helpers
# ---------------------------------------------------------------------------

def _looks_like_html(text: str) -> bool:
    """Return True if text looks like an HTML snippet rather than CSS or JS."""
    t = text.strip()
    return t.startswith("<") or bool(re.match(r"^\s*<[a-zA-Z]", t))


def _looks_like_css(text: str) -> bool:
    """Return True if text looks like a CSS rule block."""
    t = text.strip()
    # CSS rules contain selectors with braces, or at-rules
    return bool(re.search(r"[{]|@[a-zA-Z]", t))


def _looks_like_js(text: str) -> bool:
    """Return True if text looks like JavaScript (not HTML or CSS)."""
    t = text.strip()
    if _looks_like_html(t):
        return False
    # JS typically has function calls, assignments, or keywords
    js_patterns = [
        r"\bfunction\b", r"\bdocument\b", r"\bwindow\b", r"\bconst\b",
        r"\blet\b", r"\bvar\b", r"\baddEventListener\b", r"\bquerySelector\b",
        r"=>", r"\bconsole\b", r"\bif\s*\(", r"\breturn\b",
    ]
    return any(re.search(p, t) for p in js_patterns)


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------

def _propose_patch(
    profile: RecommenderProfile,
    cluster: IssueCluster,
    html_content: str,
    ui_context: str,
    ui_analysis: Optional[UIAnalysis] = None,
    overlapping_selectors: list[str] = [],
    design_tokens: dict = {},
) -> Optional[PatchProposal]:

    system = RECOMMENDER_SYSTEM.format(
        cluster_id=profile.cluster_id,
        recommender_id=profile.recommender_id,
    )

    overlap_note = ""
    if overlapping_selectors:
        overlap_note = (
            f"\n\nWARNING — SWARM OVERLAP: Selectors also targeted by peer agents: "
            f"{overlapping_selectors}. Note in side_effects."
        )

    html_snippet = _extract_relevant_html(html_content, profile.affected_elements)
    global_styles = _extract_global_styles(html_content)

    # Cap large JSON blobs to prevent token explosion
    ui_analysis_json = ui_analysis.model_dump_json(indent=2) if ui_analysis else "None provided"
    design_tokens_json = json.dumps(design_tokens, indent=2)
    if len(ui_analysis_json) > 2000:
        ui_analysis_json = ui_analysis_json[:2000] + "\n... [truncated]"
    if len(design_tokens_json) > 1000:
        design_tokens_json = design_tokens_json[:1000] + "\n... [truncated]"

    user = RECOMMENDER_USER.format(
        cluster_id=profile.cluster_id,
        cluster_label=profile.cluster_label,
        dominant_severity=profile.dominant_severity,
        dominant_category=str(cluster.dominant_category),
        affected_elements=", ".join(profile.affected_elements) or "see individual issues",
        fix_strategy_hint=profile.fix_strategy_hint,
        representative_description=profile.cluster_summary,
        issues_detail=_format_issues_detail(cluster.issues),
        html_content=html_snippet,
        global_styles=global_styles,
        ui_context=ui_context,
        ui_analysis_json=ui_analysis_json,
        design_tokens_json=design_tokens_json,
    ) + overlap_note

    prompt_size = len(system) + len(user)
    logger.info("recommender.prompt_size",
                recommender_id=profile.recommender_id,
                prompt_chars=prompt_size,
                system_chars=len(system),
                user_chars=len(user))

    raw, error = _call_recommender_llm(system, user, task="propose_patch")
    if error:
        logger.error("recommender.llm_error",
                     recommender_id=profile.recommender_id, error=error)
        return None

    # ── R5: Multi-pass self-critique if confidence is low ────────────────
    # DISABLED: critique_and_refine causes a second LLM call which compounds
    # rate limiting. With limited API quotas, we prefer one good call over
    # two calls with the risk of both failing.
    #
    # try:
    #     data = json.loads(raw)
    #     conf = data.get("confidence", 0.5)
    #     if conf < 0.8:
    #         logger.info("recommender.low_confidence_triggering_critique", 
    #                     recommender_id=profile.recommender_id, conf=conf)
    #         refined_raw = _critique_and_refine(profile, cluster, html_snippet, raw)
    #         if refined_raw:
    #             refined_data = json.loads(refined_raw)
    #             if "refined_proposal" in refined_data:
    #                 data = refined_data["refined_proposal"]
    #                 raw = json.dumps(data)
    #                 logger.info("recommender.critique_successful", 
    #                             recommender_id=profile.recommender_id)
    # except Exception as e:
    #     logger.warning("recommender.critique_failed", error=str(e))


    try:
        data = json.loads(raw)

        # Unwrap single-key container {"proposal": {...}}
        if isinstance(data, dict) and len(data) == 1:
            val = next(iter(data.values()))
            if isinstance(val, dict) and "patch_id" in val:
                data = val

        # Defaults
        if not data.get("patch_id"):
            data["patch_id"] = f"{profile.recommender_id}_{profile.cluster_id}_{uuid.uuid4().hex[:6]}"
        data.setdefault("cluster_id", profile.cluster_id)
        data.setdefault("recommender_id", profile.recommender_id)
        data.setdefault("severity_addressed", profile.dominant_severity)
        data.setdefault("rationale", data.get("description", "No rationale provided"))
        data.setdefault("confidence", 0.5)

        # Normalise patch_type
        patch_type = _normalise_patch_type(data.get("patch_type", "html_attribute"))
        data["patch_type"] = patch_type

        # ── CSS patch: css_snippet is authoritative ────────────────────────
        if patch_type in _CSS_TYPES:
            css = data.get("css_snippet", "")
            after = data.get("after_snippet", "")

            # If css_snippet is empty but after_snippet looks like CSS, promote it
            if not css and after and _looks_like_css(after):
                data["css_snippet"] = after
                logger.debug("recommender.css_promoted_from_after_snippet",
                             recommender_id=profile.recommender_id)
            elif not css and after and not _looks_like_html(after):
                # after_snippet might be CSS even without braces (e.g. property:value)
                data["css_snippet"] = after

            # after_snippet must be null for CSS patches (not an HTML change)
            data["after_snippet"] = None
            # before_snippet should be "" for CSS injections
            if not data.get("before_snippet"):
                data["before_snippet"] = ""

        # ── JS patch: js_snippet is authoritative ──────────────────────────
        elif patch_type in _JS_TYPES:
            js = data.get("js_snippet", "")
            after = data.get("after_snippet", "")

            # If js_snippet is empty, try to recover from after_snippet
            if not js and after:
                if _looks_like_js(after):
                    # after_snippet contains real JS — promote it
                    data["js_snippet"] = after
                    logger.debug("recommender.js_promoted_from_after_snippet",
                                 recommender_id=profile.recommender_id)
                elif _looks_like_html(after):
                    # after_snippet is HTML — LLM confused patch_type vs after_snippet
                    # Skip second LLM call to avoid rate limit compounding;
                    # downgrade to html_attribute so the patch is at least useful.
                    logger.warning(
                        "recommender.js_snippet_missing_html_in_after",
                        recommender_id=profile.recommender_id,
                        after_preview=after[:80],
                    )
                    data["patch_type"] = "html_attribute"
                    data["after_snippet"] = after
                    logger.warning("recommender.js_downgraded_to_html",
                                   recommender_id=profile.recommender_id)

            # after_snippet must be null for JS patches
            if data["patch_type"] in _JS_TYPES:
                data["after_snippet"] = None
                if not data.get("before_snippet"):
                    data["before_snippet"] = ""

                # Wrap in DOMContentLoaded if missing
                js = data.get("js_snippet", "")
                if js and "DOMContentLoaded" not in js:
                    data["js_snippet"] = (
                        'document.addEventListener("DOMContentLoaded", function() {\n'
                        f'  {js}\n'
                        '});'
                    )

        # ── HTML patch: after_snippet is authoritative ─────────────────────
        else:
            if not data.get("before_snippet"):
                data["before_snippet"] = ""
            if not data.get("after_snippet"):
                data["after_snippet"] = data.get("before_snippet", "")

        return PatchProposal(**data)

    except Exception as e:
        logger.error("recommender.proposal_parse_error",
                     recommender_id=profile.recommender_id,
                     error=str(e), raw=raw[:500])
        return None


def _recover_js_snippet(
    profile: RecommenderProfile,
    cluster: IssueCluster,
    html_snippet: str,
    ui_context: str,
    parsed_data: dict,
) -> Optional[str]:
    """
    Second-chance LLM call when the recommender returned patch_type=js_snippet
    but put HTML (not JS) in after_snippet.

    Asks the LLM specifically for the JavaScript code only.
    """
    system = (
        "You are a JavaScript developer. Write a self-contained JavaScript snippet "
        "that fixes the described UI issue. "
        "Output ONLY valid JSON: {\"js_snippet\": \"<your complete JS code>\"}\n"
        "The js_snippet value MUST:\n"
        "  1. Be wrapped in: document.addEventListener('DOMContentLoaded', function() { ... });\n"
        "  2. Use querySelector/getElementById to find elements\n"
        "  3. Be complete and self-contained — no imports or dependencies\n"
        "  4. NOT contain any HTML tags"
    )
    user = (
        f"Issue cluster: {cluster.cluster_label}\n"
        f"Description: {cluster.representative_description}\n"
        f"Individual issues:\n{_format_issues_detail(cluster.issues)}\n\n"
        f"Fix strategy: {profile.fix_strategy_hint}\n\n"
        f"Relevant HTML:\n{html_snippet[:3000]}\n\n"
        f"The previous attempt described this patch:\n"
        f"  description: {parsed_data.get('description', '')}\n"
        f"  rationale: {parsed_data.get('rationale', '')}\n\n"
        f"Write the actual JavaScript that implements this fix.\n"
        f"Output ONLY the JSON object."
    )

    raw, error = _call_recommender_llm(system, user, task="recover_js")
    if error:
        return None
    try:
        result = json.loads(raw)
        js = result.get("js_snippet", "")
        if js and _looks_like_js(js):
            return js
        return None
    except Exception:
        return None


def _fallback_proposal(
    profile: RecommenderProfile,
    cluster: IssueCluster,
) -> PatchProposal:
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
    MAX_CHARS = 4_000
    if len(html_content) <= MAX_CHARS:
        return html_content
    if affected_elements:
        target = affected_elements[0].lstrip("#.").split("[")[0]
        idx = html_content.find(target)
        if idx != -1:
            start = max(0, idx - 1_000)
            end   = min(len(html_content), idx + 3_000)
            return html_content[start:end]
    return html_content[:MAX_CHARS]


def _extract_global_styles(html_content: str) -> str:
    styles = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
    combined = "\n".join(styles).strip()
    if len(combined) > 2_000:
        return combined[:2_000] + "\n/* ... truncated ... */"
    return combined


def _critique_and_refine(
    profile: RecommenderProfile,
    cluster: IssueCluster,
    html_snippet: str,
    previous_proposal_json: str,
) -> Optional[str]:
    system = (
        "You are an expert A11y & UX auditor. Critique the following fix proposal. "
        "Does it actually solve the issue? Does it introduce new problems? "
        "Output ONLY a JSON object with: {\"critique\": \"...\", \"refined_proposal\": { ... }}"
    )
    user = (
        f"Issue: {cluster.cluster_label}\n"
        f"HTML Context:\n{html_snippet}\n\n"
        f"Previous Proposal:\n{previous_proposal_json}\n\n"
        "Provide a critique and a refined version of the proposal JSON."
    )
    raw, error = _call_recommender_llm(system, user, task="critique_refine")
    return raw if not error else None


def _call_recommender_llm(
    system: str,
    user:   str,
    task:   str,
) -> tuple[str, Optional[str]]:
    # UXAgent Fix 3: Unified LLM Router
    router = get_recommender_router()
    return router.chat_completion(
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        task=task,
    )