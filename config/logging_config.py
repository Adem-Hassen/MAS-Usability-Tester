# config/logging_config.py
"""
Logging configuration for the UI Evaluation System.

Responsibilities:
  - Configure structlog once at startup (idempotent — safe to call multiple times)
  - Bridge stdlib logging into structlog so LangGraph, httpx, google-auth all appear
  - Provide get_logger() for all modules
  - Provide context helpers to bind simulation/node metadata to all log lines

Two output formats:
  console  — colored, human-readable. Used during development.
  json     — structured JSON per line. Used in production / log ingestion (Loki, ELK).

Usage:
    # main.py — call once at startup
    from config.logging_config import setup_logging
    setup_logging(log_level="INFO", log_format="console")

    # any module
    from config.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("supervisor.start", html_path="/tmp/ui.html", personas=3)
    logger.warning("gemini.retry", attempt=2, delay=4.0)
    logger.error("parse.failed", task="ui_analysis", error="JSONDecodeError")

    # inside a persona simulation
    from config.logging_config import bind_simulation_context, clear_simulation_context
    bind_simulation_context(simulation_id="sim_abc", persona_id="persona_1")
    logger.info("step.start", step=3)   # automatically includes simulation_id + persona_id
    clear_simulation_context()

    # inside a pipeline node
    from config.logging_config import bind_node_context, clear_node_context
    bind_node_context(node="clustering_node", run_id="run_xyz")
    logger.info("clustering.start", issues=12)
    clear_node_context()
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Idempotency guard
# Structlog cannot be reconfigured once cache_logger_on_first_use=True is set.
# This flag ensures setup_logging() is safe to call from multiple places.
# ---------------------------------------------------------------------------
_configured: bool = False


# ---------------------------------------------------------------------------
# Noisy third-party loggers to silence
# Add any library that produces excessive output at INFO/DEBUG level.
# ---------------------------------------------------------------------------
_NOISY_LOGGERS: list[tuple[str, int]] = [
    ("httpx",                  logging.WARNING),
    ("httpcore",               logging.WARNING),
    ("httpcore.http11",        logging.WARNING),
    ("httpcore.connection",    logging.WARNING),
    ("google.auth",            logging.WARNING),
    ("google.auth.transport",  logging.WARNING),
    ("google.generativeai",    logging.WARNING),
    ("urllib3",                logging.WARNING),
    ("urllib3.connectionpool", logging.WARNING),
    ("playwright",             logging.WARNING),
    ("asyncio",                logging.WARNING),
    ("langgraph",              logging.WARNING),
    ("langchain",              logging.WARNING),
    ("langchain_core",         logging.WARNING),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """
    Configure structlog and stdlib logging for the entire application.

    Safe to call multiple times — only configures on the first call.
    Subsequent calls are no-ops (idempotency guard).

    Args:
        log_level:  Verbosity — "DEBUG" | "INFO" | "WARNING" | "ERROR"
        log_format: Output format — "console" (dev) | "json" (production)
    """
    global _configured
    if _configured:
        return

    level = _parse_level(log_level)

    # --- Processors shared by both formats ---
    # These run on every log event regardless of format.
    shared_processors: list[Any] = [
        # Merge any contextvars bound via bind_simulation_context() etc.
        structlog.contextvars.merge_contextvars,
        # Add log level string ("info", "warning", etc.)
        structlog.stdlib.add_log_level,
        # ISO 8601 UTC timestamp on every event
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Render stack_info if present (used by logger.exception())
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        # --- JSON format — for production log ingestion ---
        # Each log line is a single JSON object. Suitable for Loki, ELK, CloudWatch.
        processors = shared_processors + [
            # Render exception tracebacks as structured dicts (not raw strings)
            structlog.processors.dict_tracebacks,
            # Final render to JSON string
            structlog.processors.JSONRenderer(),
        ]
    else:
        # --- Console format — for local development ---
        # Colored, human-readable output with aligned columns.
        processors = shared_processors + [
            # Render exceptions as clean plain-text tracebacks
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.plain_traceback,
                sort_keys=False,
            ),
        ]

    # --- Configure structlog ---
    structlog.configure(
        processors=processors,
        # Use make_filtering_bound_logger for level-based filtering at the wrapper level.
        # This is faster than filtering inside processors.
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        # Cache the logger on first use for performance.
        # WARNING: this means setup_logging() MUST be called before any get_logger() call,
        # and MUST NOT be called again after the first get_logger() call.
        cache_logger_on_first_use=True,
    )

    # --- Configure stdlib logging ---
    # This ensures that libraries using stdlib logging (LangGraph, httpx, google-auth, etc.)
    # are also captured and formatted consistently.
    #
    # We use basicConfig only if the root logger has no handlers yet,
    # to avoid duplicate output if another library already configured it.
    if not logging.root.handlers:
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=level,
        )
    else:
        # Root logger already has handlers — just set the level
        logging.root.setLevel(level)

    # --- Silence noisy third-party loggers ---
    for logger_name, logger_level in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logger_level)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a named structlog logger for the given module.

    Args:
        name: pass __name__ from the calling module. This appears in every
              log line as the logger name, making it easy to filter by module.

    Returns:
        A structlog BoundLogger. Always use keyword arguments for fields:
            logger.info("event.name", key="value", count=3)
            logger.warning("retry", attempt=2, delay=4.0)
            logger.error("failed", error=str(e), task="ui_analysis")

    Note:
        Call setup_logging() before the first call to get_logger().
        If setup_logging() was not called, structlog uses its default
        (non-configured) behavior which may produce unformatted output.
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Simulation context helpers
# Bind structured metadata to all log calls within a simulation run.
# Uses structlog's contextvars — thread-safe and async-safe.
# ---------------------------------------------------------------------------

def bind_simulation_context(
    simulation_id: str,
    persona_id: str | None = None,
) -> None:
    """
    Bind simulation-level context to all subsequent log calls in this thread/task.

    After calling this, every logger.info() / logger.warning() etc. in any module
    will automatically include simulation_id (and persona_id if provided).

    Call at the start of each persona simulation.
    Always pair with clear_simulation_context() when the simulation ends.

    Args:
        simulation_id: unique ID for this evaluation run, e.g. "sim_abc123"
        persona_id:    persona being simulated, e.g. "persona_1". Optional.

    Example:
        bind_simulation_context("sim_abc123", "persona_2")
        logger.info("step.start", step=1)
        # logs: {..., "simulation_id": "sim_abc123", "persona_id": "persona_2", "step": 1}
    """
    ctx: dict[str, str] = {"simulation_id": simulation_id}
    if persona_id:
        ctx["persona_id"] = persona_id
    structlog.contextvars.bind_contextvars(**ctx)


def bind_node_context(node: str, run_id: str | None = None) -> None:
    """
    Bind pipeline node context to all subsequent log calls.

    Call at the start of each LangGraph node execution.
    Useful for distinguishing log lines from supervisor_node vs clustering_node
    vs recommender_node when they run in the same thread.

    Args:
        node:   name of the current node, e.g. "clustering_node"
        run_id: optional pipeline run identifier

    Example:
        bind_node_context("clustering_node", run_id="run_xyz")
        logger.info("clustering.start", issues=12)
        # logs: {..., "node": "clustering_node", "run_id": "run_xyz", "issues": 12}
    """
    ctx: dict[str, str] = {"node": node}
    if run_id:
        ctx["run_id"] = run_id
    structlog.contextvars.bind_contextvars(**ctx)


def clear_simulation_context() -> None:
    """
    Clear all bound context vars.

    Call at the end of each simulation run (in a try/finally block
    to ensure cleanup even if the simulation raises).

    Example:
        bind_simulation_context("sim_abc", "persona_1")
        try:
            run_simulation()
        finally:
            clear_simulation_context()
    """
    structlog.contextvars.clear_contextvars()


def clear_node_context() -> None:
    """
    Clear node-level context vars.
    Call at the end of each LangGraph node execution.
    """
    structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_level(log_level: str) -> int:
    """
    Convert a log level string to the corresponding stdlib logging int constant.
    Falls back to INFO if the string is unrecognised.
    """
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        # Don't crash on a bad log level — fall back to INFO and warn
        print(
            f"[logging_config] WARNING: unrecognised log_level={log_level!r}, "
            f"defaulting to INFO",
            file=sys.stderr,
        )
        return logging.INFO
    return level


def reset_logging() -> None:
    """
    Reset the idempotency guard so setup_logging() can be called again.
    Only intended for test scripts — never call this in production code.
    """
    global _configured
    _configured = False