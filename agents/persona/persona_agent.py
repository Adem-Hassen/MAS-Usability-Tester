# agents/persona/persona_agent.py
"""
Persona Agent — Perceive -> Decide -> Act loop.

Runs a single persona's full simulation against a sandboxed HTML page.
Called as a LangGraph node via Send() fan-out (one instance per persona).

Loop structure:
  1. BUILD sandbox  — strip full HTML to only elements relevant to this persona's task
  2. OPEN browser   — isolated Playwright context loaded with the sandbox
  3. LOOP (up to persona_max_steps):
       a. PERCEIVE   — extract DOMState from the live page
       b. DECIDE     — call LLM with persona profile + page state -> next action JSON
       c. VALIDATE   — check stop signals and repeat-action guard before acting
       d. ACT        — execute the action via Playwright
       e. ISSUE      — if action failed, call LLM again for deep issue analysis
       f. RECORD     — append ActionStep + any IssueReports to trace
  4. COMPLETE check — final LLM call to evaluate task completion
  5. CLOSE browser  — cleanup context
  6. CLEANUP sandbox — delete temp file

Stop conditions (any one ends the loop):
  - goal_achieved   : LLM signals all success criteria are met
  - dead_end        : LLM has no valid next action
  - max_steps       : step count >= settings.persona_max_steps
  - repeated_action : same (action_type, selector) pair seen twice
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional

from groq import Groq

from config.settings import settings
from core.state import GraphState
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
# LangGraph node entry point
# ---------------------------------------------------------------------------

def persona_node(state: GraphState) -> dict:
    """
    LangGraph node. Receives state with 'current_persona' injected by Send().
    Returns simulation result appended to simulation_results via operator.add.
    """
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
# PersonaRunner — owns the full simulation lifecycle
# ---------------------------------------------------------------------------

class PersonaRunner:

    def __init__(self, persona: PersonaProfile, state: GraphState):
        self.persona   = persona
        self.state     = state
        self.steps:    list[ActionStep]  = []
        self.issues:   list[IssueReport] = []
        self._seen_actions: set[tuple]   = set()  # repeat-action guard
        self._ui_map:  Optional[dict]    = None   # set by _understand_page before loop
        self._ui_map_summary: str        = "(UI map not yet loaded)"

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self) -> PersonaSimulationResult:
        sandbox_path = None
        try:
            # 1. Build sandbox
            sandbox_path, _ = build_sandbox(
                html_content=self.state["html_content"],
                persona=self.persona,
                html_source_path=self.state["html_source_path"],
            )
            # 2. Run loop inside browser context
            stop_reason = self._simulation_loop(sandbox_path)

        except Exception as e:
            logger.error("persona.fatal_error",
                         persona_id=self.persona.persona_id, error=str(e))
            stop_reason = StopReason.DEAD_END
            self.issues.append(_make_fatal_issue(self.persona, str(e)))

        finally:
            if sandbox_path:
                cleanup_sandbox(sandbox_path)

        # 3. Final completion check (only if loop ended normally)
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
    # Simulation loop
    # ------------------------------------------------------------------

    def _simulation_loop(self, sandbox_path: str) -> StopReason:
        with PlaywrightEngine(self.persona.persona_id) as engine:
            engine.open(sandbox_path, storage_seed=self.state.get("storage_seed"))

            # ── Mandatory page understanding before first action ──────────
            # The agent reads the full page and produces a UI map it will
            # use throughout the loop. This prevents URL hallucination.
            initial_state = engine.get_page_state()
            self._understand_page(initial_state)

            consecutive_scrolls = 0   # scroll stagnation guard
            last_scroll_y       = -1

            for step_num in range(1, settings.persona_max_steps + 1):
                # PERCEIVE
                page_state = engine.get_page_state()

                # SCROLL STAGNATION GUARD
                # If agent has scrolled 4+ times in a row without the page
                # changing position (or reaching the bottom), force a dead_end.
                # This is the root cause of the 30-scroll trace.
                current_y = page_state.scroll_position.get("y", 0)
                if action_type_last := getattr(self, "_last_action_type", None):
                    if action_type_last == "scroll":
                        if current_y == last_scroll_y:
                            # Page didn't move — already at top or bottom
                            consecutive_scrolls += 2   # punish harder for no movement
                        else:
                            consecutive_scrolls += 1
                    else:
                        consecutive_scrolls = 0
                last_scroll_y = current_y

                if consecutive_scrolls >= 4:
                    logger.info(
                        "persona.scroll_stagnation",
                        persona_id=self.persona.persona_id,
                        step=step_num,
                        consecutive=consecutive_scrolls,
                        scroll_pct=page_state.scroll_pct,
                    )
                    # Inject a synthetic dead_end so the agent reports a navigation issue
                    self.issues.append(_make_navigation_issue(
                        self.persona, step_num,
                        f"Agent scrolled {consecutive_scrolls} times without finding target. "
                        f"Page was {page_state.scroll_pct}% scrolled. "
                        f"Hidden sections present: {[s['id'] for s in page_state.hidden_sections]}",
                    ))
                    return StopReason.DEAD_END

                # DECIDE
                decision = self._decide(step_num, page_state)
                if decision is None:
                    return StopReason.DEAD_END

                action_type = decision.get("action_type", "observe")
                self._last_action_type = action_type  # track for stagnation guard
                selector    = decision.get("target_selector")
                value       = decision.get("value")
                stop_signal = decision.get("stop_signal")
                inline_issue = decision.get("issue_detected")

                # INTERCEPT navigate — the agent must not guess URLs.
                # Redirect it: fail the step with a clear error so it learns
                # to use click on nav links instead.
                if action_type == "navigate":
                    logger.info(
                        "persona.navigate_intercepted",
                        persona_id=self.persona.persona_id,
                        step=step_num,
                        value=value,
                    )
                    fake_result = ActionResult(
                        False, "navigate", None, value,
                        error_message=(
                            f"navigate is not allowed. You tried to go to {value!r} but this "
                            "page uses in-page navigation. Check your UI map for the correct "
                            "nav selector under 'activate_via' and use click instead."
                        ),
                    )
                    self._record_step(step_num, decision, page_state, fake_result)
                    deep_issues = self._analyze_failure(step_num, decision, fake_result, page_state)
                    self.issues.extend(deep_issues)
                    continue  # give the agent another chance

                # VALIDATE — stop signals
                if stop_signal == "goal_achieved":
                    self._record_step(step_num, decision, page_state, ActionResult(
                        True, action_type, selector, value))
                    return StopReason.GOAL_ACHIEVED

                if stop_signal == "dead_end":
                    result = engine.execute_action(action_type, selector, value)
                    self._record_step(step_num, decision, page_state, result)
                    if inline_issue:
                        self._record_inline_issue(step_num, inline_issue, selector, result)
                    return StopReason.DEAD_END

                # VALIDATE — repeat-action guard
                action_key = (action_type, selector)
                if action_key in self._seen_actions and action_type not in ("scroll", "observe"):
                    self._record_step(step_num, decision, page_state, ActionResult(
                        False, action_type, selector, value,
                        error_message="Repeated action — loop guard triggered"))
                    return StopReason.REPEATED_ACTION
                self._seen_actions.add(action_key)

                # ACT
                result = engine.execute_action(action_type, selector, value)
                self._record_step(step_num, decision, page_state, result)

                # Inline issue from decision prompt
                if inline_issue:
                    self._record_inline_issue(step_num, inline_issue, selector, result)

                # Deep issue analysis on failure
                if not result.success:
                    deep_issues = self._analyze_failure(step_num, decision, result, page_state)
                    self.issues.extend(deep_issues)

            return StopReason.MAX_STEPS

    # ------------------------------------------------------------------
    # LLM calls
    # ------------------------------------------------------------------

    def _decide(self, step_num: int, page_state: DOMState) -> Optional[dict]:
        """Call LLM to decide the next action. Returns parsed JSON dict or None."""
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
            ui_map_summary=self._ui_map_summary,
            success_criteria="\n".join(f"- {c}" for c in self.persona.success_criteria),
            action_history=_format_action_history(self.steps),
            page_dom_summary=page_state.to_prompt_string(),
        )
        return self._call_llm(system, user, label="decide")

    def _analyze_failure(
        self,
        step_num: int,
        decision: dict,
        result: ActionResult,
        page_state: DOMState,
    ) -> list[IssueReport]:
        """Deep issue analysis after a failed action."""
        constraints = (
            ", ".join(self.persona.accessibility_constraints)
            if self.persona.accessibility_constraints else "none"
        )
        system = ISSUE_DETECTION_SYSTEM
        user   = ISSUE_DETECTION_USER.format(
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
        )
        raw = self._call_llm(system, user, label="issue_analysis", expect_array=True)
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
                    reproduction_steps=item.get("reproduction_steps", []),
                    persona_impact=item.get("persona_impact", ""),
                ))
            except Exception as e:
                logger.warning("persona.issue_parse_error",
                               persona_id=self.persona.persona_id, error=str(e))
        return reports

    def _check_completion(self) -> tuple[bool, float, str, Optional[str]]:
        """Final LLM call to evaluate task completion after the loop ends."""
        # Build a minimal page state from last known step
        last_step = self.steps[-1] if self.steps else None
        page_summary = last_step.page_state_summary if last_step else "unknown"
        action_summary = _format_action_history(self.steps[-5:])  # last 5 steps

        system = COMPLETION_CHECK_SYSTEM
        user   = COMPLETION_CHECK_USER.format(
            persona_name=self.persona.name,
            task_goal=self.persona.task_goal,
            success_criteria="\n".join(f"- {c}" for c in self.persona.success_criteria),
            page_dom_summary=page_summary,
            action_summary=action_summary,
        )
        result = self._call_llm(system, user, label="completion_check")
        if not result:
            return False, 0.0, "", None

        return (
            bool(result.get("task_completed", False)),
            float(result.get("completion_confidence", 0.0)),
            result.get("overall_experience", ""),
            result.get("blocker_summary"),
        )

    def _understand_page(self, page_state: DOMState) -> None:
        """
        Called ONCE before the decision loop. The LLM reads the full page
        and produces a UI map — all sections, their activate_via selectors,
        and the recommended first step.

        The result is stored in self._ui_map and self._ui_map_summary.
        On failure we fall back to a plain-text summary so the loop can still run.
        """
        # Pre-check: detect redirected/broken pages before calling the LLM.
        # If the page has no interactive elements and is not the expected URL,
        # it's likely an auth-guard redirect to a missing file (e.g. index.html).
        interactive_count = len(page_state.interactive_elements)
        is_error_page = (
            interactive_count == 0
            and "file://" in page_state.url
            and page_state.url != (self.state.get("html_source_path") or "")
        )
        if interactive_count == 0:
            logger.warning(
                "persona.empty_page_detected",
                persona_id=self.persona.persona_id,
                url=page_state.url,
                title=page_state.page_title,
                hint=(
                    "Page has no interactive elements. "
                    "Possible auth-guard redirect — check storage_seed in supervisor output."
                ),
            )
            self._ui_map = {}
            self._ui_map_summary = (
                f"WARNING: The page loaded at {page_state.url!r} has NO interactive elements. "
                "This is likely an error page caused by an auth-guard redirect (e.g. "
                "localStorage check). You cannot interact with this page. "
                "Signal dead_end immediately and report a critical navigation issue."
            )
            return

        user = PAGE_UNDERSTANDING_USER.format(
            persona_name=self.persona.name,
            technical_skill=self.persona.technical_skill,
            task_goal=self.persona.task_goal,
            page_dom_summary=page_state.to_prompt_string(),
        )
        result = self._call_llm(
            PAGE_UNDERSTANDING_SYSTEM, user, label="understand_page"
        )

        if not result:
            logger.warning(
                "persona.understand_page_failed",
                persona_id=self.persona.persona_id,
            )
            self._ui_map = {}
            self._ui_map_summary = (
                "(page understanding failed — proceed with caution, "
                "only use selectors visible in INTERACTIVE ELEMENTS)"
            )
            return

        self._ui_map = result

        # Build a compact text summary to inject into every decision prompt
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
        logger.info(
            "persona.page_understood",
            persona_id=self.persona.persona_id,
            page_type=result.get("page_type"),
            sections=len(result.get("available_sections", [])),
            first_step=result.get("first_step", "")[:80],
        )

    def _call_llm(
        self,
        system: str,
        user: str,
        label: str,
        expect_array: bool = False,
    ) -> Optional[dict | list]:
        """
        Call the persona LLM via Groq.
        Returns parsed JSON dict/list or None on failure.
        Retries up to settings.llm_max_retries times with exponential backoff.
        """
        client = Groq(api_key=settings.persona_api_key)

        for attempt in range(1, settings.llm_max_retries + 1):
            try:
                logger.debug(
                    f"persona.llm.{label}",
                    persona_id=self.persona.persona_id,
                    model=settings.persona_llm_model,
                    attempt=attempt,
                )
                response = client.chat.completions.create(
                    model=settings.persona_llm_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=settings.persona_temperature,
                    max_tokens=settings.llm_max_output_tokens,
                    response_format={"type": "json_object"},
                )

                text = response.choices[0].message.content.strip()

                # Strip accidental markdown fences (some models still add them)
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
                logger.warning(
                    f"persona.llm.{label}.error",
                    persona_id=self.persona.persona_id,
                    attempt=attempt,
                    error=str(e),
                )
                if attempt < settings.llm_max_retries:
                    time.sleep(settings.llm_retry_delay_seconds * (2 ** (attempt - 1)))

        logger.error(
            f"persona.llm.{label}.all_retries_failed",
            persona_id=self.persona.persona_id,
        )
        return None

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
            # Link the most recent issue to this step
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
            page_state_summary=decision.get("page_state_summary") or page_state.visible_text[:200],
            success=result.success,
            error_message=result.error_message,
            issue_triggered=issue_id,
        ))

    def _record_inline_issue(
        self,
        step_num: int,
        inline: dict,
        selector: Optional[str],
        result: ActionResult,
    ) -> None:
        """Record an issue that was flagged inline in the decision response."""
        try:
            self.issues.append(IssueReport(
                issue_id=f"{self.persona.persona_id}_issue_{len(self.issues) + 1}",
                persona_id=self.persona.persona_id,
                persona_name=self.persona.name,
                severity=IssueSeverity(inline.get("severity", "medium")),
                category=IssueCategory(inline.get("category", "usability")),
                title=inline.get("title", "Issue detected during simulation"),
                description=inline.get("description", ""),
                affected_element=selector,
                affected_element_html=result.element_html,
                step_number=step_num,
                page_context=result.new_url or "",
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
        status = "OK" if s.success else f"FAILED: {s.error_message or 'unknown'}"
        lines.append(
            f"  Step {s.step_number}: {s.action_type} "
            f"'{s.target_description}' ({s.target_selector or 'n/a'}) "
            f"[{status}]"
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


def _make_navigation_issue(persona: PersonaProfile, step: int, detail: str) -> IssueReport:
    """Issue raised when the agent gets stuck scrolling instead of navigating."""
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
            f"and got stuck scrolling. This indicates the navigation affordance is "
            f"unclear or not perceivable. Detail: {detail}"
        ),
        step_number=step,
        page_context="",
        reproduction_steps=[
            "Open the page",
            f"Try to find the section as persona '{persona.name}' ({persona.technical_skill} skill)",
            "Observe that nav affordances are not clear enough to prevent repeated scrolling",
        ],
        persona_impact=(
            f"{persona.name} could not complete their goal because they could not "
            f"discover the correct navigation mechanism to reach the target section."
        ),
    )


def _make_fatal_issue(persona: PersonaProfile, error: str) -> IssueReport:
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
        reproduction_steps=["Run the simulation"],
        persona_impact="Persona could not interact with the UI at all.",
    )