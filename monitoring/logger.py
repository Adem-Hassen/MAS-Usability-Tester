# monitoring/logger.py


from __future__ import annotations


import time

from typing import Any

import structlog


from config.logging_config import (
    setup_logging,
    bind_simulation_context,
    clear_simulation_context,
)

__all__ = [
    "setup_logging",
    "get_logger",
    "AgentLogger",
    "SimulationTimer",
    "bind_simulation_context",
    "clear_simulation_context",
    "log_run_summary",
]


# ---------------------------------------------------------------------------
# get_logger — standard named logger for any module
# ---------------------------------------------------------------------------

def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a named structlog logger bound to the given module name.

    Args:
        name: pass __name__ from the calling module

    Returns:
        structlog BoundLogger — use keyword args for structured fields:
            logger.info("event.name", key="value", count=3)
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# AgentLogger — structured logging wrapper for agent nodes
# ---------------------------------------------------------------------------

class AgentLogger:
    """
    Logging helper for agent nodes.
    Wraps structlog with agent-specific convenience methods and
    automatically attaches agent_type + agent_id to every log entry.

    Usage:
        log = AgentLogger(agent_type="persona", agent_id="persona_abc123")
        log.step_start(step=1, action="click", target="#submit")
        log.step_end(step=1, success=True)
        log.issue_found(issue_id="p1_issue_1", severity="high", title="No label")
        log.llm_call_start(task="decision", prompt_chars=900)
        log.llm_call_end(task="decision", response_chars=320, elapsed=1.2)
    """

    def __init__(self, agent_type: str, agent_id: str) -> None:
        self._log = structlog.get_logger(f"agent.{agent_type}").bind(
            agent_type=agent_type,
            agent_id=agent_id,
        )

    # --- Lifecycle ---

    def start(self, **kwargs: Any) -> None:
        self._log.info("agent.start", **kwargs)

    def end(self, success: bool = True, **kwargs: Any) -> None:
        level = "info" if success else "warning"
        getattr(self._log, level)("agent.end", success=success, **kwargs)

    # --- Simulation steps ---

    def step_start(self, step: int, action: str, target: str | None = None, **kwargs: Any) -> None:
        self._log.debug("step.start", step=step, action=action, target=target, **kwargs)

    def step_end(self, step: int, success: bool = True, **kwargs: Any) -> None:
        level = "debug" if success else "warning"
        getattr(self._log, level)("step.end", step=step, success=success, **kwargs)

    def step_failed(self, step: int, action: str, error: str, **kwargs: Any) -> None:
        self._log.warning(
            "step.failed",
            step=step,
            action=action,
            error=error,
            **kwargs,
        )

    # --- Stop conditions ---

    def stopped(self, reason: str, steps_taken: int, task_completed: bool, **kwargs: Any) -> None:
        self._log.info(
            "simulation.stopped",
            reason=reason,
            steps_taken=steps_taken,
            task_completed=task_completed,
            **kwargs,
        )

    # --- Issues ---

    def issue_found(
        self,
        issue_id: str,
        severity: str,
        category: str,
        title: str,
        **kwargs: Any,
    ) -> None:
        level = "warning" if severity in ("critical", "high") else "info"
        getattr(self._log, level)(
            "issue.found",
            issue_id=issue_id,
            severity=severity,
            category=category,
            title=title,
            **kwargs,
        )

    # --- LLM calls ---

    def llm_call_start(self, task: str, prompt_chars: int, **kwargs: Any) -> None:
        self._log.debug("llm.call.start", task=task, prompt_chars=prompt_chars, **kwargs)

    def llm_call_end(
        self,
        task: str,
        response_chars: int,
        elapsed: float | None = None,
        **kwargs: Any,
    ) -> None:
        self._log.debug(
            "llm.call.end",
            task=task,
            response_chars=response_chars,
            elapsed_seconds=round(elapsed, 3) if elapsed else None,
            **kwargs,
        )

    def llm_call_failed(self, task: str, error: str, attempt: int = 1, **kwargs: Any) -> None:
        self._log.error(
            "llm.call.failed",
            task=task,
            error=error,
            attempt=attempt,
            **kwargs,
        )

    def llm_call_retry(self, task: str, attempt: int, delay: float, **kwargs: Any) -> None:
        self._log.warning(
            "llm.call.retry",
            task=task,
            attempt=attempt,
            delay_seconds=delay,
            **kwargs,
        )

    # --- Parse errors ---

    def parse_error(self, task: str, error: str, raw_preview: str = "", **kwargs: Any) -> None:
        self._log.error(
            "parse.error",
            task=task,
            error=error,
            raw_preview=raw_preview[:200],
            **kwargs,
        )

    # --- Generic passthrough ---

    def info(self, event: str, **kwargs: Any) -> None:
        self._log.info(event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log.debug(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log.error(event, **kwargs)


# ---------------------------------------------------------------------------
# SimulationTimer — context manager for timing any block
# ---------------------------------------------------------------------------

class SimulationTimer:
    """
    Context manager that measures elapsed time for any block.

    Usage:
        with SimulationTimer("persona_simulation") as t:
            run_simulation()
        logger.info("timing", phase="persona_simulation", elapsed=t.elapsed_seconds)

    Also logs start/end automatically if a logger is provided:
        with SimulationTimer("clustering", logger=logger) as t:
            run_clustering()
    """

    def __init__(self, label: str, logger: Any = None) -> None:
        self.label = label
        self._logger = logger
        self._start: float = 0.0
        self.elapsed_seconds: float = 0.0

    def __enter__(self) -> "SimulationTimer":
        self._start = time.perf_counter()
        if self._logger:
            self._logger.debug(f"timer.start", phase=self.label)
        return self

    def __exit__(self, *_: Any) -> None:
        self.elapsed_seconds = round(time.perf_counter() - self._start, 3)
        if self._logger:
            self._logger.debug(
                "timer.end",
                phase=self.label,
                elapsed_seconds=self.elapsed_seconds,
            )


# ---------------------------------------------------------------------------
# log_run_summary — human-readable pipeline summary printed at the end
# ---------------------------------------------------------------------------

def log_run_summary(
    report_id: str,
    html_path: str,
    num_personas: int,
    total_issues: int,
    severity_breakdown: dict[str, int],
    issues_resolved: int,
    issues_remaining: int,
    patches_applied: int,
    correction_loops: int,
    overall_score: float,
    elapsed_seconds: float,
    report_path: str,
) -> None:
    """
    Print a structured summary block at the end of a pipeline run.
    Uses the root logger so it always appears regardless of module name.
    """
    logger = structlog.get_logger("run.summary")

    divider = "─" * 56

    logger.info(divider)
    logger.info("  UI EVALUATION COMPLETE")
    logger.info(divider)
    logger.info("run.summary",
        report_id=report_id,
        html=html_path,
        personas=num_personas,
        elapsed_seconds=round(elapsed_seconds, 1),
    )
    logger.info("issues.summary",
        total=total_issues,
        critical=severity_breakdown.get("critical", 0),
        high=severity_breakdown.get("high", 0),
        medium=severity_breakdown.get("medium", 0),
        low=severity_breakdown.get("low", 0),
    )
    logger.info("resolution.summary",
        resolved=issues_resolved,
        remaining=issues_remaining,
        patches_applied=patches_applied,
        correction_loops=correction_loops,
    )
    logger.info("score", overall_score=f"{overall_score:.1f}/10")
    logger.info("report_saved", path=report_path)
    logger.info(divider)