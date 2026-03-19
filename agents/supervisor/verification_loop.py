
from __future__ import annotations

import json
from typing import Optional


from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from core.state import GraphState
from schemas.issue_schema import IssueReport, PersonaSimulationResult, IssueSeverity
from schemas.patch_schema import ResolvedPatch, UnifiedPatchSet
from schemas.report_schema import VerificationResult
from monitoring.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Verification prompt (kept inline — single-use prompt)
# ---------------------------------------------------------------------------

_VERIFICATION_SYSTEM = """\
You are a senior QA engineer reviewing whether a set of HTML patches has resolved
previously reported UI issues.

You will be given:
  - The patched HTML (or a relevant snippet)
  - A list of issues originally reported by a simulated user persona
  - The patches that were applied

For each issue, determine:
  resolved  — the patch clearly fixes this issue (element now has required attribute,
              label is present, contrast is corrected, etc.)
  remaining — the patch did not address this issue (wrong selector, incomplete fix,
              different element than expected)
  new       — a regression: a new issue was introduced by the patch (only report if obvious)

Output ONLY valid JSON — no explanation, no markdown:

{
  "persona_id": "string",
  "resolved":   ["issue_id", ...],
  "remaining":  ["issue_id", ...],
  "new_issues": [
    {
      "issue_id": "new_1",
      "title": "short title",
      "description": "what regression was introduced"
    }
  ],
  "task_completed_after_patch": true
}

Rules:
- Be conservative: mark as "resolved" only when you can see the fix in the HTML.
- If a patch targeted the wrong selector but accidentally fixed a nearby element, mark resolved.
- task_completed_after_patch: true if, given the patched HTML, the persona could now
  plausibly complete their original task goal.
- new_issues: only obvious regressions (broken structure, missing content, etc.).
  Do not hallucinate regressions.
"""

_VERIFICATION_USER = """\
Persona: {persona_name} (id={persona_id})
Task goal: {task_goal}

Original issues reported ({issue_count} total):
{issues_json}

Patches applied ({patch_count} total):
{patches_json}

Patched HTML (relevant snippet, up to 6000 chars):
{patched_html_snippet}

Verify each issue_id. Output ONLY the JSON object.
"""


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def verification_node(state: GraphState) -> dict:
    """
    LangGraph node.  Runs lightweight LLM-based verification of patch effectiveness.
    Writes verification_results and verification_passed to state.
    """
    patched_html: str          = state.get("patched_html_content") or state.get("html_content", "")
    unified: UnifiedPatchSet   = state.get("unified_patch_set")
    verified_results: list     = state.get("verified_results", [])
    correction_loop_count: int = state.get("correction_loop_count", 0)

    logger.info(
        "verification.start",
        personas=len(verified_results),
        patches=len(unified.patches) if unified else 0,
        correction_loop=correction_loop_count,
    )

    if not unified or not unified.patches:
        logger.warning("verification.no_patches — marking as passed (nothing to verify)")
        return {
            "verification_results": [],
            "verification_passed":  True,
        }

    if not verified_results:
        logger.warning("verification.no_simulation_results — nothing to verify against")
        return {
            "verification_results": [],
            "verification_passed":  True,
        }

    results: list[VerificationResult] = []

    for sim_result in verified_results:
        vr = _verify_persona(sim_result, unified.patches, patched_html)
        results.append(vr)
        logger.info(
            "verification.persona_done",
            persona_id=vr.persona_id,
            resolved=len(vr.issues_resolved),
            remaining=len(vr.issues_remaining),
            regressions=len(vr.new_issues_introduced),
            task_completed=vr.task_completed_after_patch,
        )

    passed = _compute_pass(results, state.get("verified_issues", []))

    logger.info(
        "verification.complete",
        passed=passed,
        total_personas=len(results),
        loop_count=correction_loop_count,
    )

    return {
        "verification_results": results,
        "verification_passed":  passed,
    }


# ---------------------------------------------------------------------------
# Per-persona verification
# ---------------------------------------------------------------------------

def _verify_persona(
    sim_result: PersonaSimulationResult,
    patches: list[ResolvedPatch],
    patched_html: str,
) -> VerificationResult:
    """
    Run the LLM verification for one persona.
    Returns a VerificationResult.
    """
    issues = sim_result.issues
    if not issues:
        return VerificationResult(
            persona_id=sim_result.persona_id,
            persona_name=sim_result.persona_name,
            issues_before=[],
            issues_remaining=[],
            issues_resolved=[],
            new_issues_introduced=[],
            task_completed_after_patch=sim_result.task_completed,
            fully_resolved=True,
        )

    issues_before = [iss.issue_id for iss in issues]

    # Extract a relevant snippet from patched HTML
    snippet = _extract_relevant_snippet(patched_html, issues, patches, max_chars=6_000)

    issues_json = json.dumps(
        [
            {
                "issue_id":      iss.issue_id,
                "title":         iss.title,
                "severity":      str(iss.severity),
                "category":      str(iss.category),
                "affected_element": iss.affected_element,
                "description":   iss.description[:200],
                "wcag_criterion": iss.wcag_criterion,
            }
            for iss in issues
        ],
        indent=2,
    )

    patches_json = json.dumps(
        [
            {
                "resolved_patch_id": p.resolved_patch_id,
                "target_element":    p.target_element,
                "patch_type":        str(p.patch_type),
                "description":       p.description,
                "before_snippet":    p.before_snippet[:200],
                "after_snippet":     p.after_snippet[:200],
            }
            for p in patches
        ],
        indent=2,
    )

    user = _VERIFICATION_USER.format(
        persona_name=sim_result.persona_name,
        persona_id=sim_result.persona_id,
        task_goal=sim_result.task_goal,
        issue_count=len(issues),
        issues_json=issues_json,
        patch_count=len(patches),
        patches_json=patches_json,
        patched_html_snippet=snippet,
    )

    raw, error = _call_verifier_llm(_VERIFICATION_SYSTEM, user, task="verify_persona")

    if error:
        logger.warning(
            "verification.llm_error",
            persona_id=sim_result.persona_id,
            error=error,
        )
        return _fallback_verification(sim_result, issues_before)

    try:
        data = json.loads(raw)
        resolved    = data.get("resolved", [])
        remaining   = data.get("remaining", issues_before)
        new_issues  = [ni.get("issue_id", "") for ni in data.get("new_issues", [])]
        task_done   = bool(data.get("task_completed_after_patch", sim_result.task_completed))

        # Sanity: every issue must be in resolved or remaining
        all_reported = set(issues_before)
        resolved   = [i for i in resolved  if i in all_reported]
        remaining  = [i for i in remaining if i in all_reported]

        # Issues not mentioned in either → treat as remaining
        mentioned  = set(resolved) | set(remaining)
        unmentioned = [i for i in issues_before if i not in mentioned]
        remaining  += unmentioned

        fully_resolved = _is_fully_resolved(sim_result, resolved, remaining)

        return VerificationResult(
            persona_id=sim_result.persona_id,
            persona_name=sim_result.persona_name,
            issues_before=issues_before,
            issues_remaining=remaining,
            issues_resolved=resolved,
            new_issues_introduced=[ni for ni in new_issues if ni],
            task_completed_after_patch=task_done,
            fully_resolved=fully_resolved,
        )

    except Exception as e:
        logger.warning(
            "verification.parse_error",
            persona_id=sim_result.persona_id,
            error=str(e),
        )
        return _fallback_verification(sim_result, issues_before)


# ---------------------------------------------------------------------------
# Pass/fail computation
# ---------------------------------------------------------------------------

def _compute_pass(
    results: list[VerificationResult],
    verified_issues: list[IssueReport],
) -> bool:
    """
    Returns True if the verification threshold is met.

    Threshold: settings.verification_resolution_threshold of critical+high
    issues must be resolved.  If there are no critical/high issues, passes
    if ≥ 50% of all issues are resolved.
    """
    # Build severity map
    sev_map: dict[str, str] = {}
    for iss in verified_issues:
        sev_map[iss.issue_id] = str(iss.severity)

    critical_high_before:    list[str] = []
    critical_high_remaining: list[str] = []

    all_before:    int = 0
    all_remaining: int = 0

    for vr in results:
        all_before    += len(vr.issues_before)
        all_remaining += len(vr.issues_remaining)
        for iid in vr.issues_before:
            sev = sev_map.get(iid, "medium")
            if sev in ("critical", "high"):
                critical_high_before.append(iid)
        for iid in vr.issues_remaining:
            sev = sev_map.get(iid, "medium")
            if sev in ("critical", "high"):
                critical_high_remaining.append(iid)

    if critical_high_before:
        resolved_critical_high = len(critical_high_before) - len(critical_high_remaining)
        ratio = resolved_critical_high / len(critical_high_before)
        passed = ratio >= settings.verification_resolution_threshold
        logger.info(
            "verification.threshold_check",
            critical_high_before=len(critical_high_before),
            critical_high_remaining=len(critical_high_remaining),
            ratio=round(ratio, 3),
            threshold=settings.verification_resolution_threshold,
            passed=passed,
        )
        return passed

    # No critical/high issues — use overall resolution ratio
    if all_before == 0:
        return True
    ratio = (all_before - all_remaining) / all_before
    passed = ratio >= 0.5
    logger.info(
        "verification.threshold_check_low_severity",
        all_before=all_before,
        all_remaining=all_remaining,
        ratio=round(ratio, 3),
        passed=passed,
    )
    return passed


def _is_fully_resolved(
    sim_result: PersonaSimulationResult,
    resolved: list[str],
    remaining: list[str],
) -> bool:
    """True if no critical or high issues remain for this persona."""
    return not any(
        iss.issue_id in remaining and str(iss.severity) in ("critical", "high")
        for iss in sim_result.issues
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _extract_relevant_snippet(
    html: str,
    issues: list[IssueReport],
    patches: list[ResolvedPatch],
    max_chars: int,
) -> str:
    """
    Return the most relevant portion of the patched HTML for the LLM.
    Prefers the region around the first affected element.
    """
    if len(html) <= max_chars:
        return html

    # Find first affected selector that appears in the HTML
    selectors = [iss.affected_element for iss in issues if iss.affected_element]
    selectors += [p.target_element for p in patches]

    for sel in selectors:
        base = sel.lstrip("#.").split("[")[0].split(":")[0]
        idx  = html.find(base)
        if idx != -1:
            start = max(0, idx - 1_500)
            end   = min(len(html), idx + max_chars - 1_500)
            return html[start:end]

    return html[:max_chars]


def _fallback_verification(
    sim_result: PersonaSimulationResult,
    issues_before: list[str],
) -> VerificationResult:
    """Fallback: assume nothing was resolved when LLM call fails."""
    return VerificationResult(
        persona_id=sim_result.persona_id,
        persona_name=sim_result.persona_name,
        issues_before=issues_before,
        issues_remaining=issues_before,
        issues_resolved=[],
        new_issues_introduced=[],
        task_completed_after_patch=False,
        fully_resolved=False,
    )


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _call_verifier_llm(
    system: str,
    user:   str,
    task:   str,
) -> tuple[str, Optional[str]]:
    """
    Uses the supervisor LLM (strongest model) for patch verification —
    needs precise HTML reading ability.
    Rate-limiting handled by groq_chat_completion (semaphore + backoff).
    """
    return groq_chat_completion(
        api_key     = settings.supervisor_api_key,
        model       = settings.supervisor_llm_model,
        messages    = [{"role": "system", "content": system},
                       {"role": "user",   "content": user}],
        temperature = 0.1,
        max_tokens  = getattr(settings, 'verifier_max_tokens', settings.llm_max_output_tokens),
        task        = task,
    )