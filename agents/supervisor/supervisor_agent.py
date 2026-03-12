# agents/supervisor/supervisor_agent.py
"""
Supervisor Node — fully implemented.

Pipeline:
  1. Read HTML file from disk
  2. Call Gemini: HTML → UIAnalysis (structured JSON)
  3. Call Gemini: UIAnalysis → list[PersonaProfile] (structured JSON)
  4. Validate both outputs with Pydantic
  5. Write to graph state for fan-out

Gemini is called with response_mime_type="application/json" to enforce
structured output without markdown fences.
"""

from __future__ import annotations
import json
from pathlib import Path

from groq import Groq

from config.settings import settings
from core.state import GraphState
from schemas.persona_schema import UIAnalysis, PersonaProfile
from prompts.supervisor_prompts import (
    UI_ANALYSIS_SYSTEM, UI_ANALYSIS_USER,
    PERSONA_GENERATION_SYSTEM, PERSONA_GENERATION_USER,
    RECOMMENDER_PROFILE_SYSTEM, RECOMMENDER_PROFILE_USER,
)
from schemas.issue_schema import (
    IssueReport, IssueCluster, IssueCategory, IssueSeverity,
    TraceVerification, TraceVerdict, StepVerification,
    RecommenderProfile, RecommenderFocus,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def supervisor_node(state: GraphState) -> dict:
    """
    LangGraph node. Reads HTML, produces UIAnalysis + personas.
    Returns partial state update.
    """
    logger.info("supervisor.start", html_path=state["html_source_path"])

    # 1. Read HTML
    html_content, error = _read_html(state["html_source_path"])
    if error:
        return {"pipeline_error": error}

    ui_context = state.get("ui_context", "General web UI")

    # 2. Analyze UI structure
    ui_analysis, error = _analyze_ui(html_content, ui_context)
    if error:
        return {"pipeline_error": f"UI analysis failed: {error}"}

    logger.info(
        "supervisor.analysis_complete",
        ui_type=ui_analysis.ui_type,
        critical_paths=len(ui_analysis.critical_paths),
        interactive_elements=len(ui_analysis.interactive_elements),
        a11y_risk=ui_analysis.accessibility_risk_level,
    )

    # 3. Generate personas
    personas, error = _generate_personas(ui_analysis, ui_context)
    if error:
        return {"pipeline_error": f"Persona generation failed: {error}"}

    logger.info("supervisor.personas_generated", count=len(personas))
    for p in personas:
        logger.info(
            "supervisor.persona",
            id=p.persona_id,
            name=p.name,
            skill=p.technical_skill,
            constraints=p.accessibility_constraints,
        )

    # 4. Detect storage requirements (auth guards, feature flags, etc.)
    storage_seed = _detect_storage_requirements(html_content)
    if storage_seed:
        logger.info(
            "supervisor.storage_seed_detected",
            localStorage_keys=list(storage_seed.get("localStorage", {}).keys()),
            sessionStorage_keys=list(storage_seed.get("sessionStorage", {}).keys()),
        )

    return {
        "html_content": html_content,
        "ui_analysis": ui_analysis,
        "personas": personas,
        "storage_seed": storage_seed,
        "simulation_results": [],
        "patch_proposals": [],
        "correction_loop_count": 0,
        "verification_passed": False,
    }


# ---------------------------------------------------------------------------
# Storage requirements detection
# ---------------------------------------------------------------------------

def _detect_storage_requirements(html_content: str) -> dict:
    """
    Scan the HTML source for localStorage / sessionStorage reads.
    For every key the page reads, inject a safe dummy value so auth
    guards and feature flags don't redirect the browser to a missing page.

    Returns: {"localStorage": {"key": "value", ...}, "sessionStorage": {...}}
    Both dicts may be empty.

    Detection strategy — regex over the raw source:
      localStorage.getItem('key')
      localStorage.getItem("key")
      sessionStorage.getItem('key')
    """
    import re

    seeds: dict = {"localStorage": {}, "sessionStorage": {}}

    # Match getItem('key') or getItem("key")
    pattern = r'(localStorage|sessionStorage)\s*\.\s*getItem\s*\(\s*["\'](.*?)["\'"]\s*\)'
    for match in re.finditer(pattern, html_content):
        store, key = match.group(1), match.group(2)
        if not key:
            continue
        # Choose a safe seed value based on key name heuristics
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


# ---------------------------------------------------------------------------
# Step 1: Read HTML
# ---------------------------------------------------------------------------

def _read_html(path: str) -> tuple[str, str | None]:
    """Returns (html_content, error_message). error_message is None on success."""
    try:
        content = Path(path).read_text(encoding="utf-8")
        if not content.strip():
            return "", "HTML file is empty"
        return content, None
    except FileNotFoundError:
        return "", f"HTML file not found: {path}"
    except Exception as e:
        return "", f"Failed to read HTML file: {e}"


# ---------------------------------------------------------------------------
# Step 2: UI Analysis via Gemini
# ---------------------------------------------------------------------------

def _analyze_ui(html_content: str, ui_context: str) -> tuple[UIAnalysis | None, str | None]:
    """Calls Gemini to produce a structured UIAnalysis from raw HTML."""
    user_prompt = UI_ANALYSIS_USER.format(
        ui_context=ui_context,
        html_content=html_content,
    )

    raw_json, error = _call_gemini(
        system_prompt=UI_ANALYSIS_SYSTEM,
        user_prompt=user_prompt,
        task="ui_analysis",
    )
    if error:
        return None, error

    try:
        data = json.loads(raw_json)
        analysis = UIAnalysis(**data)
        return analysis, None
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("supervisor.ui_analysis_parse_error", error=str(e), raw=raw_json[:500])
        return None, f"Failed to parse UIAnalysis: {e}"


# ---------------------------------------------------------------------------
# Step 3: Persona Generation via Gemini
# ---------------------------------------------------------------------------

def _generate_personas(
    ui_analysis: UIAnalysis,
    ui_context: str,
) -> tuple[list[PersonaProfile] | None, str | None]:
    """Calls Gemini to produce N PersonaProfile objects from the UIAnalysis."""
    user_prompt = PERSONA_GENERATION_USER.format(
        ui_context=ui_context,
        ui_analysis_json=ui_analysis.model_dump_json(indent=2),
        max_num_personas=settings.max_num_personas,
    )

    system_prompt = PERSONA_GENERATION_SYSTEM.format(
        max_num_personas=settings.max_num_personas,
    )

    raw_json, error = _call_gemini(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        task="persona_generation",
    )
    if error:
        return None, error

    try:
        data = json.loads(raw_json)

        # Gemini sometimes wraps array in {"personas": [...]} — unwrap defensively
        if isinstance(data, dict):
            data = data.get("personas", data.get("persona_profiles", list(data.values())[0]))

        if not isinstance(data, list):
            return None, f"Expected JSON array for personas, got: {type(data)}"

        personas = []
        for i, item in enumerate(data):
            if "persona_id" not in item or not item["persona_id"]:
                item["persona_id"] = f"persona_{i + 1}"
            personas.append(PersonaProfile(**item))

        if len(personas) == 0:
            return None, "LLM returned zero personas"

        return personas, None

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("supervisor.persona_parse_error", error=str(e), raw=raw_json[:500])
        return None, f"Failed to parse PersonaProfiles: {e}"


# ---------------------------------------------------------------------------
# Gemini call helper
# ---------------------------------------------------------------------------

def _call_gemini(
    system_prompt: str,
    user_prompt: str,
    task: str,
) -> tuple[str, str | None]:
    """
    Single Groq API call using the supervisor's dedicated API key and model.
    Runs Llama-3-70B via Groq for fast, high-quality structured JSON output.
    Returns (raw_json_string, error_message).
    """
    try:
        client = Groq(api_key=settings.supervisor_api_key)

        logger.info(f"supervisor.groq_call.{task}.start",
                    model=settings.supervisor_llm_model)

        response = client.chat.completions.create(
            model=settings.supervisor_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=settings.supervisor_temperature,
            max_tokens=settings.llm_max_output_tokens,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()

        # Defensive strip of markdown fences
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        logger.info(f"supervisor.groq_call.{task}.complete", chars=len(raw))
        return raw, None

    except Exception as e:
        logger.error(f"supervisor.groq_call.{task}.error", error=str(e))
        return "", f"Groq call failed ({task}): {e}"


# ===========================================================================
# analysis_node — post-simulation supervisor pass
# ===========================================================================

def analysis_node(state: GraphState) -> dict:
    """
    LangGraph node — trace integrity verification only.

    Cross-checks each action step against UIAnalysis + raw HTML using
    deterministic rules (no LLM). Writes verified_issues to state so
    clustering_node can pick it up next.

    Rules:
      INVALID — hallucinated navigate targets, click/type with no selector,
                browser-level network errors. Issues from these steps are discarded.
      SUSPECT — selector absent from HTML/UIAnalysis. Issues kept, step flagged.
      VALID   — everything else, including genuine runtime failures.
    """
    logger.info("analysis.start",
                personas=len(state.get("simulation_results", [])))

    simulation_results = state.get("simulation_results", [])
    html_content       = state.get("html_content", "")
    ui_analysis        = state.get("ui_analysis")

    if not simulation_results:
        logger.warning("analysis.no_simulation_results")
        return {"trace_verifications": [], "verified_issues": []}

    logger.info("analysis.trace_verification.start", count=len(simulation_results))
    trace_verifications, discarded_ids = _verify_traces(
        simulation_results, html_content, ui_analysis
    )

    # Build verified simulation results:
    #   - Keep only traces whose overall_verdict is VALID or SUSPECT
    #   - Within each kept trace, keep only VALID/SUSPECT steps (drop INVALID steps)
    #   - Keep only issues NOT in discarded_ids (issues from INVALID steps)
    verdict_by_persona = {tv.persona_id: tv for tv in trace_verifications}

    verified_results: list = []
    verified_issues:  list[IssueReport] = []

    for result in simulation_results:
        tv = verdict_by_persona.get(result.persona_id)
        # Drop entire trace if overall verdict is INVALID (>40% bad steps)
        if tv and tv.overall_verdict == TraceVerdict.INVALID:
            logger.info("analysis.trace_dropped", persona_id=result.persona_id,
                        reason="overall verdict INVALID")
            continue

        # Build step verdict lookup for this persona
        step_verdict = {
            sv.step_number: sv.verdict
            for sv in (tv.step_verifications if tv else [])
        }

        # Keep only VALID and SUSPECT steps in the action trace
        clean_steps = [
            step for step in result.action_trace
            if step_verdict.get(step.step_number, TraceVerdict.VALID) != TraceVerdict.INVALID
        ]

        # Keep only issues not discarded
        clean_issues = [
            iss for iss in result.issues
            if iss.issue_id not in discarded_ids
        ]

        # Rebuild result with clean trace and clean issues
        import copy
        clean_result = copy.copy(result)
        object.__setattr__(clean_result, "action_trace", clean_steps)
        object.__setattr__(clean_result, "issues", clean_issues)

        verified_results.append(clean_result)
        verified_issues.extend(clean_issues)

    total_raw     = sum(len(r.issues) for r in simulation_results)
    total_traces  = len(simulation_results)
    dropped_traces = total_traces - len(verified_results)

    logger.info(
        "analysis.trace_verification.complete",
        total_traces=total_traces,
        dropped_traces=dropped_traces,
        total_issues=total_raw,
        verified_issues=len(verified_issues),
        discarded=len(discarded_ids),
    )

    return {
        "trace_verifications": trace_verifications,
        "verified_results":    verified_results,
        "verified_issues":     verified_issues,
    }


def recommender_profile_node(state: GraphState) -> dict:
    """
    LangGraph node — supervisor generates one RecommenderProfile per cluster.

    Called after clustering_node has written issue_clusters to state.
    The supervisor uses its existing UI knowledge (UIAnalysis + HTML context)
    to write a targeted fix brief for each Recommender Agent.
    """
    issue_clusters = state.get("issue_clusters", [])
    ui_analysis    = state.get("ui_analysis")
    ui_context     = state.get("ui_context", "General web UI")
    ui_type        = ui_analysis.ui_type if ui_analysis else "unknown"

    logger.info("recommender_profile_node.start", clusters=len(issue_clusters))

    if not issue_clusters:
        logger.warning("recommender_profile_node.no_clusters")
        return {"recommender_profiles": []}

    profiles = _generate_recommender_profiles(issue_clusters, ui_type, ui_context)
    logger.info("recommender_profile_node.complete", profiles=len(profiles))

    return {"recommender_profiles": profiles}


# ---------------------------------------------------------------------------
# Step 1: Trace verification
# ---------------------------------------------------------------------------

def _format_action_trace(result) -> str:
    """Format a persona's action trace as readable text for the LLM."""
    lines = []
    for step in result.action_trace:
        status = "OK" if step.success else "FAIL"
        lines.append(
            f"  Step {step.step_number} [{status}] {step.action_type}"
            + (f" → {step.target_selector}" if step.target_selector else "")
            + (f" value={step.value!r}" if step.value else "")
        )
        if step.reasoning:
            lines.append(f"    reasoning: {step.reasoning[:120]}")
        if step.error_message:
            lines.append(f"    error: {step.error_message[:120]}")
    return "\n".join(lines) if lines else "  (no steps)"


def _format_issues_text(result) -> str:
    """Format a persona's issues as readable text for the LLM."""
    if not result.issues:
        return "  (no issues reported)"
    lines = []
    for iss in result.issues:
        lines.append(
            f"  [{iss.issue_id}] step={iss.step_number} "
            f"sev={iss.severity} cat={iss.category}\n"
            f"    title: {iss.title}\n"
            f"    element: {iss.affected_element or 'n/a'}"
        )
    return "\n".join(lines)


def _verify_traces(
    simulation_results: list,
    html_content: str,
    ui_analysis=None,
) -> tuple[list[TraceVerification], set[str]]:
    """
    Rule-based trace integrity verification — no LLM calls.

    Uses the UIAnalysis the supervisor already computed (known selectors,
    interactive elements) plus structural rules to flag impossible steps.

    Rules applied per step:
      INVALID if:
        - action_type == "navigate" and value looks like an absolute path
          that does not match any known critical_path or href in the HTML
        - action_type == "click"/"type" and target_selector is None
          (agent admitted it had no selector)
        - error_message contains "ERR_FILE_NOT_FOUND" or "net::ERR"
          (browser-level failure, not a UI issue)
        - action_type == "navigate" and error shows the sandbox
          rejected it (navigate_intercepted)

      SUSPECT if:
        - target_selector is not None but does not appear anywhere
          in html_content (may be hallucinated)
        - step succeeded=False AND error contains "Timeout" but
          there is no matching element in the known interactive_elements

      VALID otherwise (including genuine failures that reveal real issues).

    Issues from INVALID steps are discarded.
    Issues from SUSPECT steps are kept but flagged in the verification.
    """
    import re

    # Build selector universe from UIAnalysis (what the supervisor knows exists)
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

    # Also extract all href/id values from raw HTML as a quick membership check
    href_pattern = re.compile(r"""href=["'](.*?)["']""")
    id_pattern   = re.compile(r"""(?:id|data-section)=["'](.*?)["']""")
    for m in href_pattern.finditer(html_content):
        known_hrefs.add(m.group(1))
    for m in id_pattern.finditer(html_content):
        known_hrefs.add("#" + m.group(1))

    all_discarded: set[str] = set()
    verifications: list[TraceVerification] = []

    for result in simulation_results:
        step_verifs: list[StepVerification] = []
        persona_discarded: list[str] = []

        # Collect issue_ids associated with each step for fast lookup
        step_to_issues: dict[int, list[str]] = {}
        for iss in result.issues:
            step_to_issues.setdefault(iss.step_number, []).append(iss.issue_id)

        for step in result.action_trace:
            verdict    = TraceVerdict.VALID
            confidence = 1.0
            reason     = "Step is consistent with known page structure."
            flag_ids   = step_to_issues.get(step.step_number, [])

            sel   = step.target_selector or ""
            val   = step.value or ""
            err   = step.error_message or ""
            atype = step.action_type

            # ── INVALID rules ────────────────────────────────────────────
            if atype == "navigate" and "navigate_intercepted" in err:
                verdict    = TraceVerdict.INVALID
                confidence = 0.95
                reason     = f"navigate to {val!r} was intercepted — URL does not exist in this page."

            elif atype == "navigate" and val.startswith(("/", "http")):
                # Check if the path appears in hrefs or critical path entries
                if val not in known_hrefs and not any(val in h for h in known_hrefs):
                    verdict    = TraceVerdict.INVALID
                    confidence = 0.9
                    reason     = f"navigate target {val!r} not found in any known href or path."

            elif atype in ("click", "type") and not sel:
                verdict    = TraceVerdict.INVALID
                confidence = 0.95
                reason     = "click/type with no target_selector — agent had no real element to act on."

            elif "ERR_FILE_NOT_FOUND" in err or "net::ERR" in err:
                verdict    = TraceVerdict.INVALID
                confidence = 0.9
                reason     = f"Browser-level network error ({err[:80]}) — page never loaded."

            # ── SUSPECT rules ────────────────────────────────────────────
            elif sel and sel not in known_selectors:
                # Selector absent from UIAnalysis — check raw HTML text for presence
                # Use a loose check: if the selector's base (tag + id/class) appears anywhere
                sel_base = sel.split(":")[0].split("[")[0]  # strip pseudo + attr
                if sel_base not in html_content:
                    verdict    = TraceVerdict.SUSPECT
                    confidence = 0.6
                    reason     = (
                        f"Selector {sel!r} not found in UIAnalysis or HTML source — "
                        "may be hallucinated, but keeping issues as soft evidence."
                    )

            elif "Timeout" in err and sel and sel not in known_selectors:
                verdict    = TraceVerdict.SUSPECT
                confidence = 0.65
                reason     = f"Timeout on unknown selector {sel!r} — element may not exist."

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

        # Overall verdict
        invalid_count = sum(1 for sv in step_verifs if sv.verdict == TraceVerdict.INVALID)
        suspect_count = sum(1 for sv in step_verifs if sv.verdict == TraceVerdict.SUSPECT)
        total         = max(len(step_verifs), 1)

        if invalid_count / total > 0.40:
            overall = TraceVerdict.INVALID
            conf    = 0.85
        elif (invalid_count + suspect_count) / total > 0.25:
            overall = TraceVerdict.SUSPECT
            conf    = 0.75
        else:
            overall = TraceVerdict.VALID
            conf    = 0.90

        valid_c   = total - invalid_count - suspect_count
        summary   = (
            f"{valid_c}/{total} steps valid, "
            f"{suspect_count} suspect, {invalid_count} invalid. "
            f"{len(persona_discarded)} issue(s) discarded."
        )

        verifications.append(TraceVerification(
            persona_id=result.persona_id,
            persona_name=result.persona_name,
            overall_verdict=overall,
            overall_confidence=conf,
            step_verifications=step_verifs,
            discarded_issue_ids=persona_discarded,
            summary=summary,
        ))

        logger.info(
            "analysis.trace_verified",
            persona_id=result.persona_id,
            verdict=overall,
            valid=valid_c,
            suspect=suspect_count,
            invalid=invalid_count,
            discarded=len(persona_discarded),
        )

    return verifications, all_discarded


# ---------------------------------------------------------------------------
# Step 3: Recommender profile generation (LLM)
# ---------------------------------------------------------------------------

def _build_clusters_json(clusters: list) -> str:
    """Compact JSON representation of clusters for the LLM prompt."""
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
                    "issue_id":       iss.issue_id,
                    "title":          iss.title,
                    "wcag_criterion": iss.wcag_criterion,
                    "severity":       str(iss.severity),
                    "affected_element": iss.affected_element,
                }
                for iss in c.issues
            ],
        })
    return json.dumps(items, indent=2)


def _generate_recommender_profiles(
    clusters: list,
    ui_type: str,
    ui_context: str,
) -> list[RecommenderProfile]:
    """
    One LLM call — supervisor generates one RecommenderProfile per cluster.
    The clusters come from sentence-transformers + HDBSCAN (no LLM involvement).
    The supervisor uses its existing HTML/UI knowledge to write targeted fix briefs.
    """
    if not clusters:
        return []

    user = RECOMMENDER_PROFILE_USER.format(
        ui_type=ui_type,
        ui_context=ui_context,
        clusters_json=_build_clusters_json(clusters),
        num_clusters=len(clusters),
    )

    raw, error = _call_gemini(
        system_prompt=RECOMMENDER_PROFILE_SYSTEM,
        user_prompt=user,
        task="recommender_profiles",
    )

    if error:
        logger.error("analysis.recommender_profiles.llm_error", error=error)
        return _fallback_recommender_profiles(clusters)

    try:
        data = json.loads(raw)
        # Unwrap {"profiles": [...]} if needed
        if isinstance(data, dict):
            data = next(iter(data.values()))
        if not isinstance(data, list):
            raise ValueError(f"Expected list, got {type(data)}")

        profiles = []
        for i, item in enumerate(data):
            profiles.append(RecommenderProfile(
                recommender_id=item.get("recommender_id", f"rec_{i+1}"),
                cluster_id=item.get("cluster_id", f"cluster_{i+1}"),
                cluster_label=item.get("cluster_label", ""),
                focus=RecommenderFocus(item.get("focus", "mixed")),
                cluster_summary=item.get("cluster_summary", ""),
                dominant_severity=item.get("dominant_severity", "medium"),
                affected_elements=item.get("affected_elements", []),
                wcag_references=item.get("wcag_references", []),
                fix_strategy_hint=item.get("fix_strategy_hint", ""),
                priority=int(item.get("priority", i + 1)),
            ))
        return profiles

    except Exception as e:
        logger.error("analysis.recommender_profiles.parse_error", error=str(e))
        return _fallback_recommender_profiles(clusters)


def _fallback_recommender_profiles(clusters: list) -> list[RecommenderProfile]:
    """Minimal profiles used when LLM call fails — keeps pipeline unblocked."""
    _cat_focus = {
        "accessibility": "accessibility", "usability": "usability",
        "navigation": "navigation", "form": "form", "clarity": "clarity",
    }
    return [
        RecommenderProfile(
            recommender_id=f"rec_{i+1}",
            cluster_id=c.cluster_id,
            cluster_label=c.cluster_label,
            focus=RecommenderFocus(_cat_focus.get(str(c.dominant_category), "mixed")),
            cluster_summary=c.representative_description,
            dominant_severity=str(c.dominant_severity),
            affected_elements=c.affected_elements,
            wcag_references=[],
            fix_strategy_hint=(
                f"Review the {c.issue_count} {c.dominant_category} issue(s) "
                f"and propose targeted HTML fixes for: "
                f"{', '.join(c.affected_elements[:3]) or 'affected elements'}."
            ),
            priority=i + 1,
        )
        for i, c in enumerate(clusters)
    ]