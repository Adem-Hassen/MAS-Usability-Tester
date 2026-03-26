# agents/persona/persona_agent.py
"""
Persona Agent — Perceive -> Decide -> Act loop.

Key addition in this version: WorkingMemory dataclass.
  - Maintained by Python after every step — never by the LLM.
  - Injected as a compact, structured block into every DECISION_USER call.
  - Tracks: page_phase, fields_filled, fields_required, last_action,
    observe_count, steps_remaining.

page_phase is the most impactful field:
  filling_form      → still filling required fields
  submitted         → submit button was just clicked
  awaiting_redirect → page is loading after submit
  success           → task done
  stuck             → blocked

observe_count is enforced in Python: if the LLM returns 3 consecutive
observe actions, Python forces a dead_end rather than burning all steps.

Repeat-action guard remains: sliding 3-step window for clicks only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from config.settings import settings
from tools.rate_limiter import groq_chat_completion
from schemas.persona_schema import PersonaProfile
from schemas.issue_schema import (
    PersonaSimulationResult, StopReason,
    ActionStep, IssueReport, IssueSeverity, IssueCategory,
)
from prompts.persona_prompts import (
    PAGE_UNDERSTANDING_SYSTEM, PAGE_UNDERSTANDING_USER,
    DECISION_SYSTEM, DECISION_USER,
    ISSUE_DETECTION_SYSTEM, ISSUE_DETECTION_USER,
    COMPLETION_CHECK_SYSTEM, COMPLETION_CHECK_USER,
)
from agents.persona.agent_sandbox import build_sandbox, cleanup_sandbox
from agents.persona.playwright_engine import PlaywrightEngine, DOMState, ActionResult
from monitoring.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# WorkingMemory — maintained by Python, injected into every LLM call
# ---------------------------------------------------------------------------

class PagePhase(str, Enum):
    FILLING_FORM      = "filling_form"
    SUBMITTED         = "submitted"
    AWAITING_REDIRECT = "awaiting_redirect"
    SUCCESS           = "success"
    STUCK             = "stuck"


@dataclass
class WorkingMemory:
    """
    Compact ground-truth state object updated after every step.
    Serialised to a human-readable string and injected into DECISION_USER.
    Never modified by the LLM — only by PersonaRunner._update_memory().
    """
    page_phase:       PagePhase        = PagePhase.FILLING_FORM
    fields_filled:    dict[str, str]   = field(default_factory=dict)
    fields_required:  list[str]        = field(default_factory=list)
    last_action:      str              = "No actions taken yet."
    observe_count:    int              = 0   # consecutive observe counter
    steps_remaining:  int              = 0

    def format(self) -> str:
        """Return a compact human-readable block for injection into the prompt."""
        filled_lines = (
            "\n".join(f"    {sel}: '{val}'" for sel, val in self.fields_filled.items())
            if self.fields_filled else "    (none)"
        )
        required_lines = (
            "\n".join(f"    {sel}" for sel in self.fields_required)
            if self.fields_required else "    (ALL FIELDS FILLED — click submit next)"
        )
        return (
            f"page_phase      : {self.page_phase.value}\n"
            f"fields_filled   :\n{filled_lines}\n"
            f"fields_required :\n{required_lines}\n"
            f"last_action     : {self.last_action}\n"
            f"observe_count   : {self.observe_count}  "
            f"{'⚠ TAKE A REAL ACTION NOW' if self.observe_count >= 2 else ''}\n"
            f"steps_remaining : {self.steps_remaining}"
        )


# ---------------------------------------------------------------------------
# LangGraph node entry point
# ---------------------------------------------------------------------------

def persona_node(state: dict) -> dict:
    persona: PersonaProfile = state["current_persona"]
    logger.info("persona.start", persona_id=persona.persona_id,
                name=persona.name, goal=persona.task_goal)

    runner = PersonaRunner(persona, state)
    result = runner.run()

    logger.info(
        "persona.done",
        persona_id=persona.persona_id,
        stop_reason=result.stop_reason,
        steps=result.steps_taken,
        issues=len(result.issues),
        completed=result.task_completed,
    )
    return {"simulation_results": [result]}


# ---------------------------------------------------------------------------
# PersonaRunner
# ---------------------------------------------------------------------------

class PersonaRunner:

    def __init__(self, persona: PersonaProfile, state: dict):
        self.persona  = persona
        self.state    = state
        self.steps:   list[ActionStep]  = []
        self.issues:  list[IssueReport] = []
        self._ui_map: Optional[dict]    = None
        self._ui_map_summary: str       = "(UI map not yet loaded)"

        # Working memory — single source of truth for task state
        self._mem = WorkingMemory(
            steps_remaining=settings.persona_max_steps,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> PersonaSimulationResult:
        sandbox_path = None
        try:
            sandbox_path, _ = build_sandbox(
                html_content=self.state["html_content"],
                persona=self.persona,
                html_source_path=self.state["html_source_path"],
            )
            stop_reason = self._simulation_loop(sandbox_path)

        except Exception as e:
            logger.error("persona.fatal_error",
                         persona_id=self.persona.persona_id, error=str(e))
            stop_reason = StopReason.DEAD_END
            self.issues.append(_make_fatal_issue(
                self.persona, str(e),
                UI_page=self.state.get("html_source_path", "")
            ))

        finally:
            if sandbox_path:
                cleanup_sandbox(sandbox_path)

        task_completed, confidence, experience, blocker = False, 0.0, "", None
        if self.steps:
            task_completed, confidence, experience, blocker = self._check_completion()

        if not experience:
            experience = _default_experience(self.persona, stop_reason, self.steps)

        return PersonaSimulationResult(
            persona_id=self.persona.persona_id,
            persona_name=self.persona.name,
            task_goal=self.persona.task_goal,
            selection_rationale=getattr(self.persona, "selection_rationale", ""),
            stop_reason=stop_reason,
            steps_taken=len(self.steps),
            action_trace=self.steps,
            issues=self.issues,
            task_completed=task_completed,
            completion_confidence=confidence,
            overall_experience=experience,
            blocker_summary=blocker,
        )

    # ------------------------------------------------------------------
    # Working memory update — called after every step
    # ------------------------------------------------------------------

    def _update_memory(
        self,
        step_num:    int,
        action_type: str,
        selector:    Optional[str],
        value:       Optional[str],
        result:      ActionResult,
    ) -> None:
        """
        Update WorkingMemory based on the outcome of the last action.
        This is the ONLY place WorkingMemory is mutated.
        """
        self._mem.steps_remaining = settings.persona_max_steps - step_num

        # Outcome string for last_action
        outcome = "OK" if result.success else f"FAILED: {result.error_message or 'unknown'}"
        val_str = f" value='{value}'" if value else ""
        self._mem.last_action = (
            f"{action_type} '{selector or 'page'}'{val_str} → [{outcome}]"
        )

        # Track filled fields
        if action_type == "type" and result.success and selector:
            self._mem.fields_filled[selector] = value or ""
            # Remove from required if it was there
            if selector in self._mem.fields_required:
                self._mem.fields_required.remove(selector)

        # Observe counter — reset on any real action
        if action_type == "observe":
            self._mem.observe_count += 1
        else:
            self._mem.observe_count = 0

        # Page phase transitions
        if action_type == "click" and result.success:
            # Heuristic: if we clicked a submit-like button, move to submitted
            sel_lower = (selector or "").lower()
            desc_lower = ""
            if self.steps:
                desc_lower = (self.steps[-1].target_description or "").lower()
            submit_keywords = ("submit", "login", "sign", "register",
                               "create", "place", "order", "checkout", "pay")
            if any(k in sel_lower or k in desc_lower for k in submit_keywords):
                if self._mem.page_phase == PagePhase.FILLING_FORM:
                    self._mem.page_phase = PagePhase.SUBMITTED
                    logger.info("persona.memory.phase_submitted",
                                persona_id=self.persona.persona_id, step=step_num)

        elif self._mem.page_phase == PagePhase.SUBMITTED and action_type == "observe":
            # One observe after submit → check if redirect happened
            if result.new_url and result.new_url != self.state.get("html_source_path", ""):
                self._mem.page_phase = PagePhase.SUCCESS
            else:
                self._mem.page_phase = PagePhase.AWAITING_REDIRECT

        elif self._mem.page_phase == PagePhase.AWAITING_REDIRECT:
            self._mem.page_phase = PagePhase.SUCCESS

    def _init_required_fields(self, page_state: DOMState) -> None:
        """
        Populate fields_required from the page's interactive elements.
        Called once after page understanding completes.
        Input-type elements that are not buttons and not already filled.
        """
        required = []
        for el in page_state.interactive_elements:
    # VisibleElement is a dataclass/model — use attribute access, not .get()
            tag  = getattr(el, "tag", "") or ""
            typ  = getattr(el, "input_type", "") or ""   # field is input_type, not type
            sel  = getattr(el, "selector", "") or ""
            if not sel:
                continue
            # Include text, email, password, tel, number — exclude button, submit, checkbox, radio
            if tag == "input" and typ not in ("button", "submit", "checkbox", "radio", "hidden", ""):
                required.append(sel)
            elif tag in ("textarea", "select"):
                required.append(sel)
        self._mem.fields_required = required
        logger.info("persona.memory.fields_required",
                    persona_id=self.persona.persona_id,
                    count=len(required), fields=required)

    # ------------------------------------------------------------------
    # Simulation loop
    # ------------------------------------------------------------------

    def _simulation_loop(self, sandbox_path: str) -> StopReason:
        with PlaywrightEngine(self.persona.persona_id) as engine:
            engine.open(sandbox_path, storage_seed=self.state.get("storage_seed"))

            initial_state = engine.get_page_state()
            self._understand_page(initial_state)
            self._init_required_fields(initial_state)

            consecutive_scrolls = 0
            last_scroll_y       = -1

            for step_num in range(1, settings.persona_max_steps + 1):
                self._mem.steps_remaining = settings.persona_max_steps - step_num

                page_state = engine.get_page_state()

                # ── Scroll stagnation guard ───────────────────────────────
                current_y = page_state.scroll_position.get("y", 0)
                if last_act := getattr(self, "_last_action_type", None):
                    consecutive_scrolls = (consecutive_scrolls + (2 if current_y == last_scroll_y else 1)) \
                        if last_act == "scroll" else 0
                last_scroll_y = current_y

                if consecutive_scrolls >= 4:
                    logger.info("persona.scroll_stagnation",
                                persona_id=self.persona.persona_id, step=step_num)
                    self.issues.append(_make_navigation_issue(
                        self.persona, step_num,
                        f"Agent scrolled {consecutive_scrolls} times without finding target.",
                        UI_page=self.state.get("html_source_path", "")))
                    return StopReason.DEAD_END

                # ── Observe-spiral guard (Python-enforced) ────────────────
                # If the LLM has been observing for 2 consecutive steps,
                # skip the LLM call entirely and force a decision based on phase.
                if self._mem.observe_count >= 3:
                    logger.warning("persona.observe_spiral_broken",
                                   persona_id=self.persona.persona_id, step=step_num,
                                   phase=self._mem.page_phase.value)
                    if self._mem.page_phase in (PagePhase.SUBMITTED,
                                                PagePhase.AWAITING_REDIRECT,
                                                PagePhase.SUCCESS):
                        # We submitted — call it done
                        self._mem.page_phase = PagePhase.SUCCESS
                        return StopReason.GOAL_ACHIEVED
                    else:
                        return StopReason.DEAD_END

                # ── LLM decision ──────────────────────────────────────────
                decision = self._decide(step_num, page_state)
                if decision is None:
                    return StopReason.DEAD_END

                action_type  = decision.get("action_type", "observe")
                self._last_action_type = action_type
                selector     = decision.get("target_selector")
                value        = decision.get("value")
                stop_signal  = decision.get("stop_signal")
                inline_issue = decision.get("issue_detected")

                # ── Intercept navigate ────────────────────────────────────
                if action_type == "navigate":
                    fake_result = ActionResult(
                        False, "navigate", None, value,
                        error_message=(
                            f"navigate is not allowed. Tried {value!r} — use click on "
                            "the correct nav selector from your UI map instead."
                        ),
                    )
                    self._record_step(step_num, decision, page_state, fake_result)
                    self._update_memory(step_num, action_type, selector, value, fake_result)
                    if inline_issue:
                        self._record_inline_issue(step_num, inline_issue, selector, fake_result)
                    self.issues.extend(
                        self._analyze_failure(step_num, decision, fake_result, page_state))
                    continue

                # ── Stop signals ──────────────────────────────────────────
                if stop_signal == "goal_achieved":
                    ok = ActionResult(True, action_type, selector, value)
                    self._record_step(step_num, decision, page_state, ok)
                    self._update_memory(step_num, action_type, selector, value, ok)
                    if inline_issue:
                        self._record_inline_issue(step_num, inline_issue, selector, ok)
                    return StopReason.GOAL_ACHIEVED

                if stop_signal == "dead_end":
                    result = engine.execute_action(action_type, selector, value)
                    self._record_step(step_num, decision, page_state, result)
                    self._update_memory(step_num, action_type, selector, value, result)
                    if inline_issue:
                        self._record_inline_issue(step_num, inline_issue, selector, result)
                    return StopReason.DEAD_END

                # ── Repeat-action guard (sliding 3-step window, clicks only) ──
                if action_type == "click" and selector:
                    recent_clicks = [
                        (s.action_type, s.target_selector)
                        for s in self.steps[-3:]
                        if s.action_type == "click"
                    ]
                    if (action_type, selector) in recent_clicks:
                        logger.info("persona.repeat_guard",
                                    persona_id=self.persona.persona_id,
                                    step=step_num, selector=selector)
                        self._record_step(step_num, decision, page_state, ActionResult(
                            False, action_type, selector, value,
                            error_message="Repeated action — loop guard triggered"))
                        return StopReason.REPEATED_ACTION

                # ── Execute ───────────────────────────────────────────────
                result = engine.execute_action(action_type, selector, value)
                self._record_step(step_num, decision, page_state, result)
                self._update_memory(step_num, action_type, selector, value, result)

                # Inline issue on every step (primary accessibility detection path)
                if inline_issue:
                    self._record_inline_issue(step_num, inline_issue, selector, result)

                # Deep failure analysis
                if not result.success:
                    self.issues.extend(
                        self._analyze_failure(step_num, decision, result, page_state))

            return StopReason.MAX_STEPS

    # ------------------------------------------------------------------
    # LLM calls
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        system: str,
        user:   str,
        label:  str,
        expect_array: bool = False,
    ) -> Optional[dict | list]:
        raw, error = groq_chat_completion(
            api_key     = settings.persona_api_key,
            model       = settings.persona_llm_model,
            messages    = [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature = settings.persona_temperature,
            max_tokens  = getattr(settings, "persona_max_tokens", settings.llm_max_output_tokens),
            task        = f"persona.{label}.{self.persona.persona_id}",
        )

        if error:
            logger.warning(f"persona.llm.{label}.error",
                           persona_id=self.persona.persona_id, error=error)
            return None

        try:
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            parsed = json.loads(text)

            if expect_array and not isinstance(parsed, list):
                parsed = [parsed] if isinstance(parsed, dict) else []
            elif not expect_array and not isinstance(parsed, dict):
                raise ValueError(f"Expected dict, got {type(parsed)}")

            return parsed

        except Exception as e:
            logger.warning(f"persona.llm.{label}.parse_error",
                           persona_id=self.persona.persona_id, error=str(e))
            return None

    def _decide(self, step_num: int, page_state: DOMState) -> Optional[dict]:
        system = DECISION_SYSTEM.format(
            persona_name=self.persona.name,
            age_range=self.persona.age_range,
            technical_skill=self.persona.technical_skill,
            interaction_style=self.persona.interaction_style,
            accessibility_constraints=(
                ", ".join(self.persona.accessibility_constraints)
                if self.persona.accessibility_constraints else "none"
            ),
            cognitive_limitations=(
                ", ".join(self.persona.cognitive_limitations)
                if self.persona.cognitive_limitations else "none"
            ),
            task_goal=self.persona.task_goal,
            task_context=self.persona.task_context,
            risk_tolerance=self.persona.risk_tolerance,
        )
        user = DECISION_USER.format(
            step_number=step_num,
            max_steps=settings.persona_max_steps,
            steps_remaining=self._mem.steps_remaining,
            working_memory=self._mem.format(),
            ui_map_summary=self._ui_map_summary,
            success_criteria="\n".join(f"- {c}" for c in self.persona.success_criteria),
            page_dom_summary=page_state.to_prompt_string(),
            # Inline checklist values (pre-computed so LLM doesn't have to derive them)
            page_phase=self._mem.page_phase.value,
            fields_empty="YES — click submit now" if not self._mem.fields_required else
                         f"NO — still need: {', '.join(self._mem.fields_required)}",
            observe_count=self._mem.observe_count,
            last_action=self._mem.last_action,
        )
        return self._call_llm(system, user, label="decide")

    def _analyze_failure(
        self,
        step_num: int,
        decision: dict,
        result:   ActionResult,
        page_state: DOMState,
    ) -> list[IssueReport]:
        constraints = (
            ", ".join(self.persona.accessibility_constraints)
            if self.persona.accessibility_constraints else "none"
        )
        already_reported = "\n".join(
            f"  - [{i.severity}] {i.title}" for i in self.issues
        ) or "  (none)"

        user = ISSUE_DETECTION_USER.format(
            persona_name=self.persona.name,
            technical_skill=self.persona.technical_skill,
            accessibility_constraints=constraints,
            task_goal=self.persona.task_goal,
            action_type=result.action_type,
            target_description=decision.get("target_description", "unknown"),
            target_selector=result.target_selector or "n/a",
            error_message=result.error_message or "unknown error",
            element_html=result.element_html or "(not found)",
            page_state_summary=page_state.to_prompt_string()[:600],
            already_reported=already_reported,
        )
        raw = self._call_llm(ISSUE_DETECTION_SYSTEM, user,
                             label="issue_analysis", expect_array=True)
        if not isinstance(raw, list):
            return []

        reports = []
        for i, item in enumerate(raw):
            try:
                reports.append(IssueReport(
                    issue_id=f"{self.persona.persona_id}_issue_{len(self.issues) + i + 1}",
                    persona_id=self.persona.persona_id,
                    persona_name=self.persona.name,
                    severity=IssueSeverity(item.get("severity", "medium")),
                    category=IssueCategory(item.get("category", "usability")),
                    wcag_criterion=item.get("wcag_criterion"),
                    title=item.get("title", "Untitled issue"),
                    description=item.get("description", ""),
                    affected_element=item.get("affected_element", result.target_selector),
                    affected_element_html=item.get("affected_element_html", result.element_html),
                    step_number=step_num,
                    page_context=page_state.visible_text[:300],
                    UI_page=item.get("UI_page") or self.state.get("html_source_path", ""),
                    reproduction_steps=item.get("reproduction_steps", []),
                    persona_impact=item.get("persona_impact", ""),
                ))
            except Exception as e:
                logger.warning("persona.issue_parse_error",
                               persona_id=self.persona.persona_id, error=str(e))
        return reports

    def _check_completion(self) -> tuple[bool, float, str, Optional[str]]:
        last_step    = self.steps[-1] if self.steps else None
        page_summary = last_step.page_state_summary if last_step else "unknown"
        action_summary = _format_action_history(self.steps[-5:])
        last_action_summary = (
            f"{self.steps[-1].action_type} '{self.steps[-1].target_description}' "
            f"→ {'OK' if self.steps[-1].success else 'FAILED'}"
        ) if self.steps else "No actions taken."

        result = self._call_llm(
            COMPLETION_CHECK_SYSTEM,
            COMPLETION_CHECK_USER.format(
                persona_name=self.persona.name,
                task_goal=self.persona.task_goal,
                success_criteria="\n".join(f"- {c}" for c in self.persona.success_criteria),
                page_dom_summary=page_summary,
                action_summary=action_summary,
                last_action_summary=last_action_summary,
            ),
            label="completion_check",
        )
        if not result:
            return False, 0.0, "", None

        return (
            bool(result.get("task_completed", False)),
            float(result.get("completion_confidence", 0.0)),
            result.get("overall_experience", ""),
            result.get("blocker_summary"),
        )

    def _understand_page(self, page_state: DOMState) -> None:
        if len(page_state.interactive_elements) == 0:
            logger.warning("persona.empty_page_detected",
                           persona_id=self.persona.persona_id, url=page_state.url)
            self._ui_map = {}
            self._ui_map_summary = (
                f"WARNING: The page at {page_state.url!r} has NO interactive elements. "
                "Signal dead_end immediately."
            )
            return

        result = self._call_llm(
            PAGE_UNDERSTANDING_SYSTEM,
            PAGE_UNDERSTANDING_USER.format(
                persona_name=self.persona.name,
                technical_skill=self.persona.technical_skill,
                task_goal=self.persona.task_goal,
                page_dom_summary=page_state.to_prompt_string(),
            ),
            label="understand_page",
        )

        if not result:
            logger.warning("persona.understand_page_failed",
                           persona_id=self.persona.persona_id)
            self._ui_map = {}
            self._ui_map_summary = (
                "(page understanding failed — use selectors from INTERACTIVE ELEMENTS only)"
            )
            return

        self._ui_map = result
        lines = [
            f"page_type      : {result.get('page_type', '?')}",
            f"navigation     : {result.get('navigation_model', '?')}",
            f"purpose        : {result.get('page_purpose', '?')}",
            f"relevant_to_goal: {result.get('relevant_to_goal', '?')}",
            f"FIRST STEP     : {result.get('first_step', '?')}",
            "",
            "SECTIONS:",
        ]
        for s in result.get("available_sections", []):
            vis = "visible" if s.get("is_currently_visible") else "HIDDEN"
            lines.append(
                f"  [{vis}] {s.get('label', s.get('id', '?'))!r}"
                f"  activate_via={s.get('activate_via', 'n/a')!r}"
                f"  keywords={s.get('contains_keywords', [])}"
            )
        lines.append("")
        lines.append("AVAILABLE ACTIONS:")
        for a in result.get("available_actions", [])[:8]:
            lines.append(
                f"  {a.get('action_type','click')} {a.get('selector','?')} "
                f"— {a.get('description','')}"
            )
        self._ui_map_summary = "\n".join(lines)
        logger.info("persona.page_understood",
                    persona_id=self.persona.persona_id,
                    page_type=result.get("page_type"),
                    sections=len(result.get("available_sections", [])))

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def _record_step(
        self,
        step_num: int,
        decision: dict,
        page_state: DOMState,
        result: ActionResult,
    ) -> None:
        issue_id = None
        if self.issues:
            last = self.issues[-1]
            if last.step_number == step_num:
                issue_id = last.issue_id

        self.steps.append(ActionStep(
            step_number=step_num,
            action_type=decision.get("action_type", "observe"),
            target_selector=result.target_selector,
            target_description=decision.get("target_description") or "",
            value=result.value,
            reasoning=decision.get("reasoning") or "",
            page_state_summary=(
                decision.get("page_state_summary") or page_state.visible_text[:200]
            ),
            success=result.success,
            error_message=result.error_message,
            issue_triggered=issue_id,
        ))

    def _record_inline_issue(
        self,
        step_num: int,
        inline:   dict,
        selector: Optional[str],
        result:   ActionResult,
    ) -> None:
        try:
            self.issues.append(IssueReport(
                issue_id=f"{self.persona.persona_id}_issue_{len(self.issues) + 1}",
                persona_id=self.persona.persona_id,
                persona_name=self.persona.name,
                severity=IssueSeverity(inline.get("severity", "medium")),
                category=IssueCategory(inline.get("category", "usability")),
                wcag_criterion=inline.get("wcag_criterion"),
                title=inline.get("title", "Issue detected during simulation"),
                description=inline.get("description", ""),
                affected_element=selector,
                affected_element_html=result.element_html,
                step_number=step_num,
                page_context=result.new_url or "",
                UI_page=inline.get("UI_page") or self.state.get("html_source_path", ""),
                reproduction_steps=[],
                persona_impact=inline.get("persona_impact", ""),
            ))
        except Exception as e:
            logger.warning("persona.inline_issue_parse_error",
                           persona_id=self.persona.persona_id, error=str(e))


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _format_action_history(steps: list[ActionStep]) -> str:
    if not steps:
        return "No actions taken yet."
    lines = []
    for s in steps:
        outcome    = "OK" if s.success else f"FAILED: {s.error_message or 'unknown'}"
        value_part = f" value='{s.value}'" if s.value else ""
        lines.append(
            f"  Step {s.step_number}: {s.action_type} "
            f"'{s.target_description}' ({s.target_selector or 'n/a'})"
            f"{value_part} → [{outcome}]"
        )
    return "\n".join(lines)


def _default_experience(
    persona: PersonaProfile,
    stop_reason: StopReason,
    steps: list[ActionStep],
) -> str:
    reasons = {
        StopReason.GOAL_ACHIEVED:   "completed their task successfully",
        StopReason.DEAD_END:        "was blocked and could not complete their task",
        StopReason.MAX_STEPS:       f"reached the maximum of {settings.persona_max_steps} steps without completing",
        StopReason.REPEATED_ACTION: "got stuck repeating the same action",
    }
    desc = reasons.get(stop_reason, "stopped for an unexpected reason")
    return (
        f"{persona.name} {desc}. "
        f"They took {len(steps)} step(s) toward their goal: {persona.task_goal}."
    )


def _make_navigation_issue(
    persona: PersonaProfile,
    step: int,
    detail: str,
    UI_page: str = "",
) -> IssueReport:
    return IssueReport(
        issue_id=f"{persona.persona_id}_nav_stagnation_{step}",
        persona_id=persona.persona_id,
        persona_name=persona.name,
        severity=IssueSeverity.HIGH,
        category=IssueCategory.NAVIGATION,
        wcag_criterion="2.4.1 Bypass Blocks",
        title="Content not discoverable — agent resorted to repeated scrolling",
        description=(
            f"The agent could not find the target section through normal navigation "
            f"and got stuck scrolling. Detail: {detail}"
        ),
        step_number=step,
        page_context="",
        UI_page=UI_page,
        reproduction_steps=[
            "Open the page",
            f"Try to find the section as persona '{persona.name}' ({persona.technical_skill} skill)",
            "Observe that nav affordances are not clear enough to prevent repeated scrolling",
        ],
        persona_impact=(
            f"{persona.name} could not complete their goal because they could not "
            f"discover the correct navigation mechanism."
        ),
    )


def _make_fatal_issue(
    persona: PersonaProfile,
    error: str,
    UI_page: str = "",
) -> IssueReport:
    return IssueReport(
        issue_id=f"{persona.persona_id}_fatal",
        persona_id=persona.persona_id,
        persona_name=persona.name,
        severity=IssueSeverity.CRITICAL,
        category=IssueCategory.OTHER,
        title="Simulation crashed — could not run",
        description=f"The simulation failed with an unrecoverable error: {error}",
        step_number=0,
        page_context="",
        UI_page=UI_page,
        reproduction_steps=["Run the simulation"],
        persona_impact="Persona could not interact with the UI at all.",
    )