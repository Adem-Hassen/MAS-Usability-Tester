

from __future__ import annotations

import copy
import json
import uuid
import concurrent.futures
from pathlib import Path

from config.settings import settings
from tools.rate_limiter import chat_completion
from tools.llm_router import get_supervisor_router
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

    # ── 2 & 3. Parallel UI Analysis and Persona Generation ───────────────
    used_names:       list[str] = list(state.get("used_persona_names",       []))
    used_goals:       list[str] = list(state.get("used_persona_goals",       []))
    used_constraints: list[str] = list(state.get("used_persona_constraints", []))

    page_contexts: list[PageContext] = []

    def process_page(page: dict) -> PageContext | str:
        html_path    = page["html_path"]
        html_content = page["html_content"]
        ui_context   = page["ui_context"]

        # 1. UI Analysis
        user_prompt = UI_ANALYSIS_USER.format(
            ui_context=ui_context,
            html_content=preprocess_for_analysis(html_content, 5_000),
        )
        raw_analysis, analysis_error = _call_supervisor_llm(
            system_prompt=UI_ANALYSIS_SYSTEM,
            user_prompt=user_prompt,
            task="ui_analysis",
        )
        if analysis_error:
            analysis = _stub_analysis(ui_context)
        else:
            try:
                analysis = UIAnalysis(**json.loads(raw_analysis))
            except Exception:
                analysis = _stub_analysis(ui_context)

        # 2. Persona Budget
        max_personas = _persona_budget(analysis)

        # 3. Persona Generation
        personas, persona_error = _generate_personas(
            ui_analysis=analysis,
            ui_context=ui_context,
            max_personas=max_personas,
            used_names=[], # Cross-page diversity relaxed for parallel perf
            used_goals=[],
            used_constraints=[],
        )
        if persona_error:
            logger.error("supervisor.persona_generation_failed", path=html_path, error=persona_error)
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

        storage_seed = _detect_storage_requirements(html_content)

        return PageContext(
            html_source_path=html_path,
            original_html_path=html_path,
            html_content=html_content,
            ui_context=ui_context,
            storage_seed=storage_seed,
            ui_analysis=analysis,
            personas=personas,
        )

    # Execute in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(loaded))) as executor:
        results = list(executor.map(process_page, loaded))

    for res in results:
        if isinstance(res, str):
            logger.error("supervisor.process_page_error", error=res)
            continue
        page_contexts.append(res)
        # Update used lists locally
        used_names       += [p.name for p in res.personas]
        used_goals       += [p.task_goal for p in res.personas]
        used_constraints += [c for p in res.personas for c in p.accessibility_constraints]

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
        raw_issue_count = len(result.issues)
        if tv and tv.overall_verdict == TraceVerdict.INVALID:
            logger.info("analysis.trace_dropped",
                        persona_id=result.persona_id, reason="verdict INVALID",
                        raw_issues=raw_issue_count)
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

        logger.debug("analysis.persona_issues",
                     persona_id=result.persona_id,
                     raw=raw_issue_count,
                     clean=len(clean_issues),
                     discarded=raw_issue_count - len(clean_issues))

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

    import yaml
    
    # Load predefined library
    library_path = Path("config/persona_templates.yaml").resolve()
    if not library_path.exists():
        return None, "config/persona_templates.yaml not found"
        
    try:
        persona_library_raw = library_path.read_text(encoding="utf-8")
        persona_library = yaml.safe_load(persona_library_raw).get("personas", [])
    except Exception as e:
        return None, f"Failed to load persona library: {e}"

    # Filter personas by UI Type relevance and minify for the prompt
    current_ui_type = str(ui_analysis.ui_type).lower()
    relevant_personas = []
    prompt_library = []
    for p in persona_library:
        ui_types = [t.lower() for t in p.get("ui_types", [])]
        if "*" in ui_types or current_ui_type in ui_types or current_ui_type == "other":
            relevant_personas.append(p)
            prompt_library.append({
                "base_id": p["id"],
                "name": p["name"],
                "constraints": p.get("accessibility_constraints", []) + p.get("cognitive_limitations", [])
            })

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
        diversity_block = (
            "\n\nDIVERSITY REQUIREMENTS — strictly enforce:\n"
            + "\n".join(parts)
            + "\n\nEach persona MUST differ in task goal."
        )

    user_prompt = PERSONA_GENERATION_USER.format(
        persona_library_json=json.dumps(prompt_library, indent=2),
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
    if not raw or not raw.strip():
        logger.error("supervisor.persona_generation_empty_response")
        return None, "LLM returned empty response for persona generation"

    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("personas", data.get("persona_profiles", list(data.values())[0]))
        if isinstance(data, str):
            data = json.loads(data) 

        lib_map = {p.get("id"): p for p in relevant_personas if "id" in p}
        personas = []
        for i, item in enumerate(data):
            base_id = item.get("base_id")
            if not base_id or base_id not in lib_map:
                continue
                
            base_profile = lib_map[base_id].copy()
            if "id" in base_profile:
                del base_profile["id"]
            if "ui_types" in base_profile:
                del base_profile["ui_types"]
                
            merged = {
                **base_profile,
                "persona_id": f"persona_{i+1}_{uuid.uuid4().hex[:4]}",
                "task_goal": item.get("task_goal", "Explore the page"),
                "task_context": item.get("task_context", "Testing UI"),
                "selection_rationale": item.get("selection_rationale", ""),
                "entry_point": item.get("entry_point"),
                "success_criteria": item.get("success_criteria", []),
            }
            personas.append(PersonaProfile(**merged))

        if not personas:
            return None, "LLM returned zero personas or failed to match library IDs"

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
    input_selectors: set[str] = set()

    if ui_analysis:
        for el in getattr(ui_analysis, "interactive_elements", []):
            if el.selector:
                k = el.selector.strip()
                known_selectors.add(k)
                tag = getattr(el, "tag", "").lower().strip("<>")
                if tag in ("input", "textarea", "select", "contenteditable"):
                    input_selectors.add(k)
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
        previous_actions:  set[tuple]            = set()

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
            
            action_sig = (atype, sel, val, err)

            if action_sig in previous_actions and atype != "observe":
                verdict, confidence = TraceVerdict.INVALID, 0.95
                reason = "Post-mortem Loop Detection: Exact identical action and consequence signature repeated."
            elif atype == "navigate" and ("navigate_intercepted" in err or "navigate is not allowed" in err):
                verdict, confidence = TraceVerdict.SUSPECT, 0.95
                reason = f"navigate to {val!r} intercepted."
            elif atype == "navigate" and val and val.startswith(("/", "http")):
                if val not in known_hrefs and not any(val in h for h in known_hrefs):
                    verdict, confidence = TraceVerdict.SUSPECT, 0.6
                    reason = f"navigate target {val!r} not in known hrefs."
            elif atype in ("click", "type") and not sel:
                verdict, confidence = TraceVerdict.INVALID, 0.95
                reason = "click/type with no target_selector."
            elif atype == "type" and sel and sel not in input_selectors:
                verdict, confidence = TraceVerdict.SUSPECT, 0.95
                reason = f"Type action on element {sel!r} which wasn't strictly identified as an input."
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
            elif atype != "observe":
                previous_actions.add(action_sig)

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
            logger.warning("supervisor.trace_dropped", persona_id=result.persona_id, invalid_ratio=f"{invalid_c}/{total}")
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
    """Uses chat_completion with provider-agnostic rate limiting."""
    if force_array:
        system_prompt = (
            system_prompt
            + '\n\nIMPORTANT: Wrap your JSON array in an object: {"items": [...]}'
        )

    router = get_supervisor_router()
    raw, error = router.chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        task=task,
    )
    if error:
        return "", error

    if not raw or not raw.strip():
        logger.error("supervisor.empty_llm_response", task=task, model=router.model)
        return "", f"LLM returned empty response for {task}"

    if force_array:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "items" in obj:
                raw = json.dumps(obj["items"])
        except Exception:
            pass

    return raw, None