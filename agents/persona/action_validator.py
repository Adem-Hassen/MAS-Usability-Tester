# agents/persona/action_validator.py
"""
UXAgent-inspired action validation layer.

Validates every LLM-generated action BEFORE it touches the DOM.
Three defensive layers:
  1. JSON schema whitelist — action must parse and match known types
  2. Required parameter check — e.g. click needs target_selector
  3. Fast-fail DOM check — Playwright locator count with short timeout
    (catches hallucinated selectors that weren't in the cached UI map)
"""

from __future__ import annotations

import json
from typing import Optional

from monitoring.logger import get_logger

logger = get_logger(__name__)


# Normalised actions (must match ActionType literal in schema)
VALID_ACTIONS = {
    "click",
    "type",
    "scroll",
    "navigate",
    "observe",
    "hover",
}

# LLMs sometimes use synonyms that _record_step later normalises.
# We MUST accept them here or the validator falsely rejects valid actions.
_SYNONYM_MAP = {
    "input":     "type",
    "type_into": "type",
    "write":     "type",
    "enter":     "type",
    "select":    "click",
    "press":     "click",
    "click_on":  "click",
    "look":      "observe",
    "scan":      "observe",
    "wait":      "observe",
    "waiting":   "observe",
}

# Map of normalised action -> required fields
REQUIRED_FIELDS = {
    "click":     ["target_selector"],
    "type":      ["target_selector", "value"],
    "scroll":    ["value"],           # direction string
    "navigate":  ["value"],           # URL string
    "observe":   [],
    "hover":     ["target_selector"],
}


class ValidationResult:
    def __init__(self, ok: bool, error: Optional[str] = None,
                 sanitized: Optional[dict] = None):
        self.ok = ok
        self.error = error
        self.sanitized = sanitized or {}


class ActionValidator:
    """
    Stateless validator.  Call validate() with the raw decision dict
    and an optional PlaywrightEngine for live DOM checks.
    """

    def validate(self, decision: dict, engine=None) -> ValidationResult:
        # 1. Schema / whitelist (normalise synonyms first)
        raw_action = str(decision.get("action_type", "")).lower().strip()
        action_type = _SYNONYM_MAP.get(raw_action, raw_action)
        if action_type not in VALID_ACTIONS:
            return ValidationResult(
                ok=False,
                error=f"Invalid action_type '{raw_action}' (normalised: '{action_type}'). Allowed: {VALID_ACTIONS}",
            )

        # 2. Required parameters
        missing = []
        for field in REQUIRED_FIELDS.get(action_type, []):
            if not decision.get(field):
                missing.append(field)
        if missing:
            return ValidationResult(
                ok=False,
                error=f"Action '{action_type}' missing required fields: {missing}",
            )

        selector = decision.get("target_selector")

        # 3. Fast-fail DOM check (only for actions that touch elements)
        if action_type in ("click", "type", "hover") and selector and engine:
            try:
                if not engine.selector_exists(selector, timeout_ms=500):
                    return ValidationResult(
                        ok=False,
                        error=(
                            f"Hallucination Blocked: selector '{selector}' "
                            f"does not exist in the current visible DOM. "
                            f"You must rely strictly on the INTERACTIVE ELEMENTS list."
                        ),
                    )
            except Exception as e:
                # If the check itself fails, log but don't block — let Playwright handle it
                logger.debug("validator.dom_check_error", error=str(e))

        return ValidationResult(
            ok=True,
            sanitized={
                "action_type": action_type,
                "target_selector": selector,
                "value": decision.get("value"),
                "stop_signal": decision.get("stop_signal"),
                "issue_detected": decision.get("issue_detected"),
                "target_description": decision.get("target_description", ""),
                "reasoning": decision.get("reasoning", ""),
                "page_state_summary": decision.get("page_state_summary", ""),
            },
        )
