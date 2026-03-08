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

import google.generativeai as genai

from config.settings import settings
from core.state import GraphState
from schemas.persona_schema import UIAnalysis, PersonaProfile
from prompts.supervisor_prompts import (
    UI_ANALYSIS_SYSTEM, UI_ANALYSIS_USER,
    PERSONA_GENERATION_SYSTEM, PERSONA_GENERATION_USER,
)
from monitoring.logger import get_logger

logger = get_logger(__name__)

# Configure Gemini client once at module load
genai.configure(api_key=settings.gemini_api_key)


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

    return {
        "html_content": html_content,
        "ui_analysis": ui_analysis,
        "personas": personas,
        "simulation_results": [],
        "patch_proposals": [],
        "correction_loop_count": 0,
        "verification_passed": False,
    }


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
            return None, "Gemini returned zero personas"

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
    Single Gemini API call with JSON output enforcement.
    Returns (raw_json_string, error_message).
    """
    try:
        model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=system_prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,        # low for deterministic structured output
                max_output_tokens=4096,
            ),
        )

        logger.info(f"supervisor.gemini_call.{task}.start")
        response = model.generate_content(user_prompt)
        raw = response.text.strip()

        # Defensive strip of markdown fences (some model versions add them)
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        logger.info(f"supervisor.gemini_call.{task}.complete", chars=len(raw))
        return raw, None

    except Exception as e:
        logger.error(f"supervisor.gemini_call.{task}.error", error=str(e))
        return "", f"Gemini call failed ({task}): {e}"