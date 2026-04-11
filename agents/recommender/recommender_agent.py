# agents/recommender/recommender_agent.py

from __future__ import annotations

import json
import re
import uuid
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
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
    overlapping_selectors: list[str],
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
                    # Make a second LLM call to get the actual JS
                    logger.warning(
                        "recommender.js_snippet_missing_html_in_after",
                        recommender_id=profile.recommender_id,
                        after_preview=after[:80],
                    )
                    js_code = _recover_js_snippet(profile, cluster, html_snippet, ui_context, data)
                    if js_code:
                        data["js_snippet"] = js_code
                    else:
                        # Downgrade to html_attribute so the patch is at least useful
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


def _extract_global_styles(html_content: str) -> str:
    styles = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL | re.IGNORECASE)
    return "\n".join(styles).strip()


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