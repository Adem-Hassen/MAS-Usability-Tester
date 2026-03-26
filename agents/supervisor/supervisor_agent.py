

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from tools.html_preprocessor import preprocess_for_analysis
from core.state import GraphState, PageContext
from schemas.persona_schema import UIAnalysis, PersonaProfile
from prompts.supervisor_prompts import (
    UI_ANALYSIS_SYSTEM, UI_ANALYSIS_USER,
    PERSONA_GENERATION_SYSTEM, PERSONA_GENERATION_USER,
    RECOMMENDER_PROFILE_SYSTEM, RECOMMENDER_PROFILE_USER,
)
from schemas.issue_schema import (
    IssueReport,
    TraceVerification, TraceVerdict, StepVerification,
    RecommenderProfile, RecommenderFocus,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# supervisor_node  (LangGraph entry node)
# =============================================================================

def supervisor_node(state: dict) -> dict:
    """
    LangGraph node.

    Reads all HTML files, runs batch UIAnalysis + per-page persona generation,
    returns a list of initialised PageContext objects (one per page) via the
    page_contexts operator.add accumulator.

    State reads:
        pages_input              list[{"html_path": str, "ui_context": str}]
        used_persona_names       list[str]
        used_persona_goals       list[str]
        used_persona_constraints list[str]

    State writes:
        page_contexts            list[PageContext]  — one per HTML page
        used_persona_names       updated accumulator
        used_persona_goals       updated accumulator
        used_persona_constraints updated accumulator
        pipeline_error           str | None
    """
    pages_input: list[dict] = state.get("pages_input", [])
    logger.info("supervisor.start", total_pages=len(pages_input))

    if not pages_input:
        return {"pipeline_error": "No pages provided — pages_input is empty."}

    # ── 1. Read all HTML files ────────────────────────────────────────────
    loaded: list[dict] = []   # {html_path, html_content, ui_context}
    read_errors: list[str] = []

    for entry in pages_input:
        html_path  = entry.get("html_path", "")
        ui_context = entry.get("ui_context", "General web UI")

        html_content, error = _read_html(html_path)
        if error:
            read_errors.append(f"{html_path}: {error}")
            logger.error("supervisor.read_error", path=html_path, error=error)
        else:
            loaded.append({
                "html_path":    html_path,
                "html_content": html_content,
                "ui_context":   ui_context,
            })

    if not loaded:
        return {
            "pipeline_error": (
                "All HTML files failed to load: " + "; ".join(read_errors)
            )
        }

    if read_errors:
        logger.warning(
            "supervisor.some_files_failed",
            failed=len(read_errors),
            loaded=len(loaded),
        )

    # ── 2. Batch UIAnalysis — one LLM call for all pages ─────────────────
    analyses, error = _batch_analyze_ui(loaded)
    if error:
        return {"pipeline_error": f"Batch UI analysis failed: {error}"}

    # ── 3. Per-page persona generation ───────────────────────────────────
    used_names:       list[str] = list(state.get("used_persona_names",       []))
    used_goals:       list[str] = list(state.get("used_persona_goals",       []))
    used_constraints: list[str] = list(state.get("used_persona_constraints", []))

    page_contexts: list[PageContext] = []

    for page, analysis in zip(loaded, analyses):
        html_path    = page["html_path"]
        html_content = page["html_content"]
        ui_context   = page["ui_context"]

        # Persona budget: proportional to page complexity
        max_personas = _persona_budget(analysis)

        personas, error = _generate_personas(
            ui_analysis=analysis,
            ui_context=ui_context,
            max_personas=max_personas,
            used_names=used_names,
            used_goals=used_goals,
            used_constraints=used_constraints,
        )
        if error:
            logger.error(
                "supervisor.persona_generation_failed",
                path=html_path, error=error,
            )
            personas = []

        logger.info(
            "supervisor.page_ready",
            path=html_path,
            ui_type=analysis.ui_type,
            personas=len(personas),
            a11y_risk=analysis.accessibility_risk_level,
        )
        for p in personas:
            logger.info(
                "supervisor.persona",
                page=Path(html_path).name,
                id=p.persona_id,
                name=p.name,
                skill=p.technical_skill,
                constraints=p.accessibility_constraints,
            )

        # Detect localStorage / sessionStorage seeds
        storage_seed = _detect_storage_requirements(html_content)

        # Accumulate diversity so next page gets different archetypes
        used_names       += [p.name for p in personas]
        used_goals       += [p.task_goal for p in personas]
        used_constraints += [c for p in personas for c in p.accessibility_constraints]

        ctx = PageContext(
            html_source_path=html_path,
            html_content=html_content,
            ui_context=ui_context,
            storage_seed=storage_seed,
            ui_analysis=analysis,
            personas=personas,
        )
        page_contexts.append(ctx)

    logger.info(
        "supervisor.complete",
        pages=len(page_contexts),
        total_personas=sum(len(c.personas) for c in page_contexts),
    )

    return {
        "page_contexts":            page_contexts,
        "used_persona_names":       used_names,
        "used_persona_goals":       used_goals,
        "used_persona_constraints": used_constraints,
    }


# =============================================================================
# analysis_node  (post-simulation trace verification)
# =============================================================================

def analysis_node(state: dict) -> dict:
    """
    Trace integrity verification — reads/writes flat state keys.
    Called via _ctx_to_flat expansion in graph.py wrapper nodes.
    """
    simulation_results = state.get("simulation_results", [])
    html_content       = state.get("html_content", "")
    ui_analysis        = state.get("ui_analysis")
    html_path          = state.get("html_source_path", "unknown")

    logger.info("analysis.start",
                page=Path(html_path).name,
                simulations=len(simulation_results))

    if not simulation_results:
        logger.warning("analysis.no_simulation_results", page=Path(html_path).name)
        return {"trace_verifications": [], "verified_results": [], "verified_issues": []}

    trace_verifications, discarded_ids = _verify_traces(
        simulation_results, html_content, ui_analysis
    )

    verdict_by_persona = {tv.persona_id: tv for tv in trace_verifications}
    verified_results: list = []
    verified_issues:  list[IssueReport] = []

    for result in simulation_results:
        tv = verdict_by_persona.get(result.persona_id)
        if tv and tv.overall_verdict == TraceVerdict.INVALID:
            logger.info("analysis.trace_dropped",
                        persona_id=result.persona_id, reason="verdict INVALID")
            continue

        step_verdict = {
            sv.step_number: sv.verdict
            for sv in (tv.step_verifications if tv else [])
        }
        clean_steps  = [
            s for s in result.action_trace
            if step_verdict.get(s.step_number, TraceVerdict.VALID) != TraceVerdict.INVALID
        ]
        clean_issues = [
            i for i in result.issues
            if i.issue_id not in discarded_ids
        ]

        clean_result = copy.copy(result)
        object.__setattr__(clean_result, "action_trace", clean_steps)
        object.__setattr__(clean_result, "issues",       clean_issues)

        verified_results.append(clean_result)
        verified_issues.extend(clean_issues)

    logger.info("analysis.complete",
                page=Path(html_path).name,
                verified_issues=len(verified_issues),
                discarded=len(discarded_ids))

    return {
        "trace_verifications": trace_verifications,
        "verified_results":    verified_results,
        "verified_issues":     verified_issues,
    }


# =============================================================================
# recommender_profile_node
# =============================================================================

def recommender_profile_node(state: dict) -> dict:
    """
    Generates RecommenderProfile objects — reads/writes flat state keys.
    Called via _ctx_to_flat expansion in graph.py wrapper nodes.
    """
    issue_clusters = state.get("issue_clusters", [])
    ui_analysis    = state.get("ui_analysis")
    ui_context     = state.get("ui_context", "General web UI")
    html_path      = state.get("html_source_path", "unknown")
    ui_type        = ui_analysis.ui_type if ui_analysis else "unknown"

    logger.info("recommender_profile_node.start",
                page=Path(html_path).name, clusters=len(issue_clusters))

    if not issue_clusters:
        logger.warning("recommender_profile_node.no_clusters")
        return {"recommender_profiles": []}

    profiles = _generate_recommender_profiles(issue_clusters, ui_type, ui_context)
    logger.info("recommender_profile_node.complete",
                page=Path(html_path).name, profiles=len(profiles))
    return {"recommender_profiles": profiles}


# =============================================================================
# Batch UI analysis  (all pages in one LLM call)
# =============================================================================

_BATCH_ANALYSIS_SYSTEM = """\
You are a senior UX engineer and accessibility specialist.
You will analyze MULTIPLE HTML pages from the same web application.
Analyzing them together lets you understand the overall user journey
(e.g. login -> dashboard -> checkout) and identify cross-page patterns.

For EACH page, output a UIAnalysis JSON object. Return a JSON array — one
object per page, in the SAME ORDER as the input pages.

Each UIAnalysis must match this exact schema:
{
  "ui_purpose": "string",
  "ui_type": "login form | dashboard | checkout | registration | landing | other",
  "accessibility_risk_level": "low | medium | high",
  "detected_issues_hint": ["string", ...],
  "critical_paths": [
    {
      "path_id": "string",
      "name": "string",
      "steps": ["step 1", ...],
      "accessibility_sensitive": true,
      "entry_selector": "CSS selector or null"
    }
  ],
  "interactive_elements": [
    {
      "tag": "string",
      "selector": "CSS selector",
      "label": "string or null",
      "input_type": "string or null",
      "is_accessible": true,
      "notes": "string or null"
    }
  ]
}

Output ONLY a valid JSON array — no explanation, no markdown.
"""

_BATCH_ANALYSIS_USER = """\
Application context: {app_context}

You are analysing {n_pages} page(s) from the same application.

{pages_block}

Analyse each page. Output ONLY the JSON array (one UIAnalysis per page, same order).
"""


def _batch_analyze_ui(
    loaded: list[dict],
) -> tuple[list[UIAnalysis], str | None]:
    """
    Single LLM call that analyses ALL pages together.
    Returns list[UIAnalysis] in same order as loaded[].

    Token budget: each page gets at most _per_page_chars() characters so that
    N pages never exceed ~20 K tokens in the batch prompt.  Groq's context
    window is 128 K but the JSON response size also matters — staying under
    20 K input tokens avoids the empty-choices response.
    """
    n = len(loaded)

    # Dynamic per-page char budget: total cap / number of pages, min 1500
    TOTAL_CHAR_BUDGET = 15_000
    per_page_chars    = max(1500, TOTAL_CHAR_BUDGET // n)

    # Build the pages block: one section per page
    pages_block_parts = []
    for i, page in enumerate(loaded, 1):
        html = preprocess_for_analysis(page["html_content"], per_page_chars)
#
        pages_block_parts.append(
            f"=== PAGE {i} ===\n"
            f"File: {Path(page['html_path']).name}\n"
            f"Context: {page['ui_context']}\n\n"
            f"{html}"
        )

    # Derive a short app context from all ui_context strings
    all_contexts = [p["ui_context"] for p in loaded]
    app_context  = " / ".join(all_contexts) if len(all_contexts) > 1 else all_contexts[0]

    user_prompt = _BATCH_ANALYSIS_USER.format(
        app_context=app_context,
        n_pages=n,
        pages_block="\n\n".join(pages_block_parts),
    )

    logger.info("supervisor.batch_analysis_prompt_size",
                pages=n,
                per_page_chars=per_page_chars,
                total_chars=len(user_prompt))

    raw, error = _call_supervisor_llm(
        system_prompt=_BATCH_ANALYSIS_SYSTEM,
        user_prompt=user_prompt,
        task="batch_ui_analysis",
        force_array=True,
    )
    if error:
        return [], error

    try:
        data = json.loads(raw)
        # Unwrap {"pages": [...]} container
        if isinstance(data, dict):
            data = next(iter(data.values()))
        if not isinstance(data, list):
            raise ValueError(f"Expected array, got {type(data)}")

        analyses = []
        for item in data:
            analyses.append(UIAnalysis(**item))

        # If LLM returned fewer items than pages, pad with stubs
        while len(analyses) < n:
            analyses.append(_stub_analysis(loaded[len(analyses)]["ui_context"]))

        return analyses[:n], None

    except Exception as e:
        logger.error("supervisor.batch_analysis_parse_error",
                     error=str(e), raw=raw[:500])
        # Fallback: analyse each page individually
        return _fallback_individual_analysis(loaded)




def _fallback_individual_analysis(
    loaded: list[dict],
) -> tuple[list[UIAnalysis], str | None]:
    """Per-page fallback when batch call fails."""
    analyses = []
    for page in loaded:
        user = UI_ANALYSIS_USER.format(
            ui_context=page["ui_context"],
            html_content=preprocess_for_analysis(page["html_content"], 10_000),
        )
        raw, error = _call_supervisor_llm(
            system_prompt=UI_ANALYSIS_SYSTEM,
            user_prompt=user,
            task="ui_analysis_fallback",
        )
        if error:
            analyses.append(_stub_analysis(page["ui_context"]))
            continue
        try:
            analyses.append(UIAnalysis(**json.loads(raw)))
        except Exception:
            analyses.append(_stub_analysis(page["ui_context"]))
    return analyses, None


def _stub_analysis(ui_context: str) -> UIAnalysis:
    return UIAnalysis(
        ui_purpose=ui_context,
        ui_type="other",
        accessibility_risk_level="high",
        detected_issues_hint=["Analysis failed — stub used"],
        critical_paths=[],
        interactive_elements=[],
    )


# =============================================================================
# Persona budget — how many personas per page
# =============================================================================

def _persona_budget(analysis: UIAnalysis) -> int:
    """
    Calculate the persona budget for a page based on its complexity.

    Heuristic:
      - Base budget = settings.max_num_personas
      - Reduce for very simple pages (few elements, low risk)
      - Increase (up to max) for complex pages (many paths, high risk)

    Always between 1 and settings.max_num_personas.
    """
    max_p = settings.max_num_personas

    n_elements = len(analysis.interactive_elements)
    n_paths    = len(analysis.critical_paths)
    risk       = analysis.accessibility_risk_level  # low | medium | high

    # Score 0-10
    score = (
        min(n_elements / 5, 3)    # up to 3 pts for element count
        + min(n_paths,      3)    # up to 3 pts for critical paths
        + {"low": 0, "medium": 2, "high": 4}.get(str(risk), 2)
    )

    # Map score to persona count: score 0-3 → 1-2, 4-6 → 3, 7-10 → max
    if score <= 3:
        budget = max(1, max_p // 3)
    elif score <= 6:
        budget = max(2, max_p // 2)
    else:
        budget = max_p

    return min(budget, max_p)


# =============================================================================
# Persona generation
# =============================================================================

def _generate_personas(
    ui_analysis: UIAnalysis,
    ui_context:  str,
    max_personas: int,
    used_names:       list[str],
    used_goals:       list[str],
    used_constraints: list[str],
) -> tuple[list[PersonaProfile] | None, str | None]:

    diversity_block = ""
    if used_names or used_goals or used_constraints:
        parts = []
        if used_names:
            parts.append(f"Names already used (DO NOT reuse): {', '.join(used_names)}")
        if used_goals:
            parts.append(
                "Task goals already covered:\n"
                + "\n".join(f"  - {g}" for g in used_goals[:10])
            )
        if used_constraints:
            unique = list(dict.fromkeys(used_constraints))[:10]
            parts.append(
                "Constraint profiles already used (ensure variety):\n"
                + "\n".join(f"  - {c}" for c in unique)
            )
        diversity_block = (
            "\n\nDIVERSITY REQUIREMENTS — strictly enforce:\n"
            + "\n".join(parts)
            + "\n\nEach persona MUST differ in name, task goal AND constraint profile."
        )

    user_prompt = PERSONA_GENERATION_USER.format(
        ui_context=ui_context,
        ui_analysis_json=ui_analysis.model_dump_json(indent=2),
        max_num_personas=max_personas,
    ) + diversity_block

    system_prompt = PERSONA_GENERATION_SYSTEM.format(
        max_num_personas=max_personas,
    )

    raw, error = _call_supervisor_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        task="persona_generation",
        force_array=True
    )
    if error:
        return None, error

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("personas", data.get("persona_profiles", list(data.values())[0]))
        if isinstance(data, str):
            data = json.loads(data) 

        personas = []
        for i, item in enumerate(data):
            if not item.get("persona_id"):
                item["persona_id"] = f"persona_{i+1}"
            personas.append(PersonaProfile(**item))

        if not personas:
            return None, "LLM returned zero personas"

        return personas[:max_personas], None

    except Exception as e:
        logger.error("supervisor.persona_parse_error", error=str(e), raw=raw[:500])
        return None, f"Failed to parse PersonaProfiles: {e}"


# =============================================================================
# Storage requirements detection
# =============================================================================

def _detect_storage_requirements(html_content: str) -> dict:
    import re
    seeds: dict = {"localStorage": {}, "sessionStorage": {}}
    pattern = r'(localStorage|sessionStorage)\s*\.\s*getItem\s*\(\s*["\']([^"\']+)["\']\s*\)'
    for match in re.finditer(pattern, html_content):
        store, key = match.group(1), match.group(2)
        if not key:
            continue
        lkey = key.lower()
        if any(x in lkey for x in ("email", "mail")):
            value = "test.user@example.com"
        elif any(x in lkey for x in ("user", "name", "username")):
            value = "test_user"
        elif any(x in lkey for x in ("token", "auth", "jwt", "session", "access")):
            value = "sandbox_token_abc123"
        elif any(x in lkey for x in ("id", "userid", "user_id")):
            value = "user_001"
        elif any(x in lkey for x in ("role", "permission", "level")):
            value = "user"
        elif any(x in lkey for x in ("flag", "feature", "enabled")):
            value = "true"
        elif any(x in lkey for x in ("lang", "locale", "language")):
            value = "en"
        elif any(x in lkey for x in ("theme", "mode", "color")):
            value = "light"
        else:
            value = "sandbox_value"
        seeds[store][key] = value
    return seeds


# =============================================================================
# HTML reader
# =============================================================================

def _read_html(path: str) -> tuple[str, str | None]:
    try:
        content = Path(path).read_text(encoding="utf-8")
        if not content.strip():
            return "", f"HTML file is empty: {path}"
        return content, None
    except FileNotFoundError:
        return "", f"HTML file not found: {path}"
    except Exception as e:
        return "", f"Failed to read {path}: {e}"


# =============================================================================
# Trace verification  (rule-based, no LLM)
# =============================================================================

def _verify_traces(
    simulation_results: list,
    html_content: str,
    ui_analysis=None,
) -> tuple[list[TraceVerification], set[str]]:
    import re

    known_selectors: set[str] = set()
    known_hrefs:     set[str] = set()

    if ui_analysis:
        for el in getattr(ui_analysis, "interactive_elements", []):
            if el.selector:
                known_selectors.add(el.selector.strip())
        for path in getattr(ui_analysis, "critical_paths", []):
            entry = getattr(path, "entry_selector", None)
            if entry:
                known_selectors.add(entry.strip())

    for m in re.finditer(r"""href=["'](.*?)["']""", html_content):
        known_hrefs.add(m.group(1))
    for m in re.finditer(r"""(?:id|data-section)=["'](.*?)["']""", html_content):
        known_hrefs.add("#" + m.group(1))

    all_discarded: set[str] = set()
    verifications: list[TraceVerification] = []

    for result in simulation_results:
        step_verifs:      list[StepVerification] = []
        persona_discarded: list[str]             = []

        step_to_issues: dict[int, list[str]] = {}
        for iss in result.issues:
            step_to_issues.setdefault(iss.step_number, []).append(iss.issue_id)

        for step in result.action_trace:
            verdict    = TraceVerdict.VALID
            confidence = 1.0
            reason     = "Step consistent with known page structure."
            flag_ids   = step_to_issues.get(step.step_number, [])

            sel   = step.target_selector or ""
            val   = step.value or ""
            err   = step.error_message or ""
            atype = step.action_type

            if atype == "navigate" and "navigate_intercepted" in err:
                verdict, confidence = TraceVerdict.INVALID, 0.95
                reason = f"navigate to {val!r} intercepted."
            elif atype == "navigate" and val.startswith(("/", "http")):
                if val not in known_hrefs and not any(val in h for h in known_hrefs):
                    verdict, confidence = TraceVerdict.INVALID, 0.9
                    reason = f"navigate target {val!r} not in known hrefs."
            elif atype in ("click", "type") and not sel:
                verdict, confidence = TraceVerdict.INVALID, 0.95
                reason = "click/type with no target_selector."
            elif "ERR_FILE_NOT_FOUND" in err or "net::ERR" in err:
                verdict, confidence = TraceVerdict.INVALID, 0.9
                reason = f"Browser network error: {err[:80]}"
            elif sel and sel not in known_selectors:
                sel_base = sel.split(":")[0].split("[")[0]
                if sel_base not in html_content:
                    verdict, confidence = TraceVerdict.SUSPECT, 0.6
                    reason = f"Selector {sel!r} not in UIAnalysis or HTML."
            elif "Timeout" in err and sel and sel not in known_selectors:
                verdict, confidence = TraceVerdict.SUSPECT, 0.65
                reason = f"Timeout on unknown selector {sel!r}."

            if verdict == TraceVerdict.INVALID:
                persona_discarded.extend(flag_ids)
                all_discarded.update(flag_ids)

            step_verifs.append(StepVerification(
                step_number=step.step_number,
                verdict=verdict,
                confidence=confidence,
                reason=reason,
                flagged_issue_ids=flag_ids if verdict == TraceVerdict.INVALID else [],
            ))

        invalid_c = sum(1 for sv in step_verifs if sv.verdict == TraceVerdict.INVALID)
        suspect_c = sum(1 for sv in step_verifs if sv.verdict == TraceVerdict.SUSPECT)
        total     = max(len(step_verifs), 1)

        if invalid_c / total > 0.40:
            overall, conf = TraceVerdict.INVALID, 0.85
        elif (invalid_c + suspect_c) / total > 0.25:
            overall, conf = TraceVerdict.SUSPECT, 0.75
        else:
            overall, conf = TraceVerdict.VALID, 0.90

        valid_c = total - invalid_c - suspect_c
        verifications.append(TraceVerification(
            persona_id=result.persona_id,
            persona_name=result.persona_name,
            overall_verdict=overall,
            overall_confidence=conf,
            step_verifications=step_verifs,
            discarded_issue_ids=persona_discarded,
            summary=(
                f"{valid_c}/{total} steps valid, {suspect_c} suspect, "
                f"{invalid_c} invalid. {len(persona_discarded)} issue(s) discarded."
            ),
        ))

    return verifications, all_discarded


# =============================================================================
# Recommender profile generation
# =============================================================================

def _build_clusters_json(clusters: list) -> str:
    items = []
    for c in clusters:
        items.append({
            "cluster_id":                 c.cluster_id,
            "cluster_label":              c.cluster_label,
            "dominant_category":          str(c.dominant_category),
            "dominant_severity":          str(c.dominant_severity),
            "issue_count":                c.issue_count,
            "affected_personas":          c.affected_personas,
            "affected_elements":          c.affected_elements,
            "representative_description": c.representative_description,
            "issues_summary": [
                {
                    "issue_id":         iss.issue_id,
                    "title":            iss.title,
                    "wcag_criterion":   iss.wcag_criterion,
                    "severity":         str(iss.severity),
                    "affected_element": iss.affected_element,
                }
                for iss in c.issues
            ],
        })
    return json.dumps(items, indent=2)


def _generate_recommender_profiles(
    clusters: list,
    ui_type:  str,
    ui_context: str,
) -> list[RecommenderProfile]:
    if not clusters:
        return []
 
    def _do_call(system_prompt: str, user_prompt: str) -> tuple[str, str | None]:
        return _call_supervisor_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task="recommender_profiles",
        )
 
    raw, error = _do_call(
        system_prompt=RECOMMENDER_PROFILE_SYSTEM,
        user_prompt=RECOMMENDER_PROFILE_USER.format(
            ui_type=ui_type,
            ui_context=ui_context,
            clusters_json=_build_clusters_json(clusters),
            num_clusters=len(clusters),
        ),
    )
 
    # Empty response — retry with a minimal prompt
    if not error and not raw.strip():
        logger.warning("supervisor.recommender_profiles_empty_response — retrying")
        simple_user = (
            f"Generate one RecommenderProfile JSON object per cluster.\n"
            f"UI type: {ui_type}\n"
            f"Clusters ({len(clusters)}):\n"
            + "\n".join(
                f"  cluster_id={c.cluster_id} label={c.cluster_label!r} "
                f"severity={c.dominant_severity} category={c.dominant_category} "
                f"elements={c.affected_elements[:2]}"
                for c in clusters
            )
            + "\n\nOutput ONLY a JSON array of RecommenderProfile objects."
        )
        raw, error = _do_call(
            system_prompt=RECOMMENDER_PROFILE_SYSTEM,
            user_prompt=simple_user,
        )
 
    if error or not raw.strip():
        logger.error("supervisor.recommender_profiles_llm_error",
                     error=error or "empty response after retry")
        return _fallback_recommender_profiles(clusters)
 
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = next(iter(data.values()))
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, list):
            raise ValueError(f"Expected list, got {type(data)}")
 
        profiles = []
        for i, item in enumerate(data):
            # Safe coercion for numeric fields — LLM sometimes returns strings
            try:
                num_rec = int(item.get("num_recommenders", 1))
            except (TypeError, ValueError):
                num_rec = 1
 
            try:
                priority = int(item.get("priority", i + 1))
            except (TypeError, ValueError):
                priority = i + 1
 
            profiles.append(RecommenderProfile(
                recommender_id   = item.get("recommender_id",    f"rec_{i+1}"),
                recommender_name = item.get("recommender_name",  f"Agent-{i+1}"),
                cluster_id       = item.get("cluster_id",        f"cluster_{i+1}"),
                cluster_label    = item.get("cluster_label",     ""),
                focus            = RecommenderFocus(item.get("focus", "mixed")),
                cluster_summary  = item.get("cluster_summary",   ""),
                dominant_severity= item.get("dominant_severity", "medium"),
                affected_elements= item.get("affected_elements", []),
                wcag_references  = item.get("wcag_references",   []),
                fix_strategy_hint= item.get("fix_strategy_hint", ""),
                num_recommenders = max(1, min(4, num_rec)),
                priority         = max(1, priority),
            ))
        return profiles
 
    except Exception as e:
        logger.error("supervisor.recommender_profiles_parse_error", error=str(e))
        return _fallback_recommender_profiles(clusters)
 


def _fallback_recommender_profiles(clusters: list) -> list[RecommenderProfile]:
    _focus_map  = {
        "accessibility": "accessibility", "usability": "usability",
        "navigation": "navigation", "form": "form", "clarity": "clarity",
    }
    _name_map   = {
        "accessibility": "AriaFixer", "usability": "UsabilityBot",
        "navigation": "NavSentinel", "form": "FormGuard", "clarity": "ClarityBot",
    }
    return [
        RecommenderProfile(
            recommender_id   = f"rec_{i+1}",
            recommender_name = _name_map.get(str(c.dominant_category), f"Agent-{i+1}"),
            cluster_id       = c.cluster_id,
            cluster_label    = c.cluster_label,
            focus            = RecommenderFocus(_focus_map.get(str(c.dominant_category), "mixed")),
            cluster_summary  = c.representative_description,
            dominant_severity= str(c.dominant_severity),
            affected_elements= c.affected_elements,
            wcag_references  = [],
            fix_strategy_hint= (
                f"Review the {c.issue_count} {c.dominant_category} issue(s) "
                f"and propose targeted HTML fixes for: "
                f"{', '.join(c.affected_elements[:3]) or 'affected elements'}."
            ),
            num_recommenders = min(max(1, c.issue_count // 4), 4),
            priority         = i + 1,
        )
        for i, c in enumerate(clusters)
    ]


# =============================================================================
# LLM call helper
# =============================================================================

def _call_supervisor_llm(
    system_prompt: str,
    user_prompt:   str,
    task:          str,
    force_array:   bool = False,
) -> tuple[str, str | None]:
    """Uses groq_chat_completion with Groq-aware rate limiting."""
    if force_array:
        system_prompt = (
            system_prompt
            + '\n\nIMPORTANT: Wrap your JSON array in an object: {"items": [...]}'
        )

    raw, error = groq_chat_completion(
        api_key     = settings.supervisor_api_key,
        model       = settings.supervisor_llm_model,
        messages    = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature = settings.supervisor_temperature,
        max_tokens  = getattr(settings, 'supervisor_max_tokens', settings.llm_max_output_tokens),
        task        = task,
    )
    if error:
        return "", error

    if force_array:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "items" in obj:
                raw = json.dumps(obj["items"])
        except Exception:
            pass

    return raw, None