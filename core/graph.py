# graph.py


from __future__ import annotations

import copy
import json
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from config.settings import settings
from config.logging_config import setup_logging
from core.state import GraphState, PageContext, make_initial_state
from monitoring.logger import get_logger

from agents.supervisor.supervisor_agent import (
    supervisor_node        as _supervisor_node,
    analysis_node          as _analysis_node,
    recommender_profile_node as _rec_profile_node,
)
from agents.persona.persona_agent          import persona_node          as _persona_node
from agents.persona.playwright_engine      import shutdown_shared_browser
from agents.persona.request_pool           import PersonaAsyncRequestPool
from tools.analysis.cluster_engine         import clustering_node       as _clustering_node
from agents.recommender.recommender_agent  import recommender_node      as _recommender_node
from agents.recommender.conflict_resolver  import conflict_resolver_node as _conflict_node
from agents.supervisor.patch_applicator   import patch_applicator_node  as _patch_node
from agents.supervisor.verification_loop import verification_node      as _verification_node
from agents.supervisor.report_generator         import report_generator_node  as _report_node
from tools.analysis.audit_engine import audit_node as _audit_node

from tools.analysis.design_token_extractor import design_token_node as _token_node
from tools.analysis.plugin_base import plugin_registry

# Import plugins to trigger registration
import tools.analysis.plugins.audit_plugin
import tools.analysis.plugins.token_plugin

logger = get_logger(__name__)


# =============================================================================
# PageContext <-> flat-state helpers
# =============================================================================

def _ctx_to_flat(ctx: PageContext) -> dict:
    """Expand a PageContext into the flat keys the original node functions expect."""
    return {
        "html_source_path":         ctx.html_source_path,
        "original_html_path":       ctx.original_html_path,
        "html_content":             ctx.html_content,
        "ui_context":               ctx.ui_context,
        "storage_seed":             ctx.storage_seed,
        "ui_analysis":              ctx.ui_analysis,
        "personas":                 ctx.personas,
        "simulation_results":       list(ctx.simulation_results),
        "trace_verifications":      list(ctx.trace_verifications),
        "verified_results":         list(ctx.verified_results),
        "verified_issues":          list(ctx.verified_issues),
        "issue_clusters":           list(ctx.issue_clusters),
        "recommender_profiles":     list(ctx.recommender_profiles),
        "patch_proposals":          list(ctx.patch_proposals),
        "swarm_claims":             list(ctx.swarm_claims),
        "unified_patch_set":        ctx.unified_patch_set,
        "patched_html_content":     ctx.patched_html_content,
        "total_patches_applied":    ctx.total_patches_applied,
        "verification_results":     list(ctx.verification_results),
        "verification_passed":      ctx.verification_passed,
        "correction_loop_count":    ctx.correction_loop_count,
        "report":                   ctx.report,
        "pipeline_error":           ctx.page_error,
        "audit_results":            list(ctx.audit_results),
        "design_tokens":            dict(ctx.design_tokens),
        "used_persona_names":       [],
        "used_persona_goals":       [],
        "used_persona_constraints": [],
    }


_FIELD_MAP = {
    "html_content":          "html_content",
    "ui_analysis":           "ui_analysis",
    "personas":              "personas",
    "storage_seed":          "storage_seed",
    "trace_verifications":   "trace_verifications",
    "verified_results":      "verified_results",
    "verified_issues":       "verified_issues",
    "issue_clusters":        "issue_clusters",
    "recommender_profiles":  "recommender_profiles",
    "unified_patch_set":     "unified_patch_set",
    "patched_html_content":  "patched_html_content",
    "total_patches_applied": "total_patches_applied",
    "verification_results":  "verification_results",
    "verification_passed":   "verification_passed",
    "correction_loop_count": "correction_loop_count",
    "report":                "report",
    "pipeline_error":        "page_error",
    "audit_results":         "audit_results",
    "design_tokens":         "design_tokens",
}


def _flat_to_ctx(ctx: PageContext, flat: dict) -> PageContext:
    """Merge a node's flat return dict back into a PageContext."""
    ctx = copy.copy(ctx)
    for flat_key, ctx_attr in _FIELD_MAP.items():
        if flat_key in flat:
            setattr(ctx, ctx_attr, flat[flat_key])
    return ctx


# =============================================================================
# supervisor_node  (entry — single, processes all pages)
# =============================================================================

def supervisor_node(state: dict) -> dict:
    """
    Calls the original supervisor which reads all HTML files, runs batch
    UIAnalysis, and generates personas per page.
    Stores the result in supervisor_output for _fan_out_pages to read.
    """
    logger.info("graph.supervisor_node.start",
                pages=len(state.get("pages_input", [])))
    try:
        result = _supervisor_node(state)
    except Exception as exc:
        logger.error("graph.supervisor_node.exception", error=str(exc))
        return {"pipeline_error": f"Supervisor crashed: {exc}"}

    if result.get("pipeline_error"):
        logger.error("graph.supervisor_node.pipeline_error",
                     error=result["pipeline_error"])
        return result

    page_ctxs = result.get("page_contexts", [])
    logger.info("graph.supervisor_node.done",
                pages=len(page_ctxs),
                total_personas=sum(len(c.personas) for c in page_ctxs))

    return {
        "supervisor_output":        result,
        "used_persona_names":       result.get("used_persona_names", []),
        "used_persona_goals":       result.get("used_persona_goals", []),
        "used_persona_constraints": result.get("used_persona_constraints", []),
    }


# =============================================================================
# _fan_out_pages  (edge function after supervisor_node)
# =============================================================================

def _fan_out_pages(state: dict) -> list[Send] | str:
    """
    Reads page_contexts from supervisor_output and emits one Send per page.
    Each Send injects current_page_context so page_pipeline_node can read it.
    """
    if state.get("pipeline_error"):
        logger.error("fan_out_pages.pipeline_error", error=state["pipeline_error"])
        return END

    sup_out = state.get("supervisor_output") or {}
    page_ctxs: list[PageContext] = sup_out.get("page_contexts", [])

    if not page_ctxs:
        logger.error("fan_out_pages.no_page_contexts",
                     sup_out_keys=list(sup_out.keys()) if sup_out else "None")
        return END

    logger.info("fan_out_pages.sending", pages=len(page_ctxs))
    return [
        Send("page_pipeline_node", {**state, "current_page_context": ctx})
        for ctx in page_ctxs
    ]


# =============================================================================
# page_pipeline_node  (parallel — one per page, runs full pipeline internally)
# =============================================================================

def page_pipeline_node(state: dict) -> dict:
    """
    Runs the complete pipeline for one page:
      simulate → analyse → cluster → recommend → patch → verify → report

    Receives current_page_context injected by Send().
    Runs all personas sequentially (safe, no concurrent writes).
    Returns only to Annotated accumulators (page_contexts, reports).
    """
    ctx: PageContext = state["current_page_context"]
    page_name = Path(ctx.html_source_path).name

    logger.info("page_pipeline.start", page=page_name,
                personas=len(ctx.personas))

    # ── Step 1: Persona simulations (sequential within this page) ─────────
    ctx = _run_simulations(ctx, state)

    # ── Step 1b: Analysis Plugins (A10 Plugin System) ─────────────────────
    for plugin in plugin_registry.get_plugins():
        logger.info("page_pipeline.running_plugin", plugin=plugin.plugin_id)
        ctx = plugin.run(ctx)

    # ── Step 2: Trace verification ─────────────────────────────────────────
    ctx = _run_analysis(ctx)

    if not ctx.verified_issues:
        logger.info("page_pipeline.no_issues", page=page_name)
        ctx = _run_report(ctx)
        return _page_result(ctx)

    # ── Step 3: Clustering ─────────────────────────────────────────────────
    ctx = _run_clustering(ctx)

    if not ctx.issue_clusters:
        logger.info("page_pipeline.no_clusters", page=page_name)
        ctx = _run_report(ctx)
        return _page_result(ctx)

    # ── Step 4 → 8: Recommender cycle (with correction loop) ──────────────
    for loop in range(settings.max_correction_loops + 1):
        if loop > 0:
            ctx = _prepare_correction(ctx, loop)
            ctx = _run_simulations(ctx, state)
            ctx = _run_analysis(ctx)
            ctx = _run_clustering(ctx)
            if not ctx.issue_clusters:
                break

        ctx = _run_recommender_profiles(ctx)
        ctx = _run_recommenders(ctx)      # sequential per profile
        ctx = _run_conflict_resolver(ctx)
        ctx = _run_patch_applicator(ctx)
        ctx = _run_verification(ctx)

        if ctx.verification_passed:
            logger.info("page_pipeline.verification_passed",
                        page=page_name, loop=loop)
            break
        else:
            ctx.correction_loop_count = loop + 1
            logger.info("page_pipeline.verification_failed",
                        page=page_name, loop=loop,
                        max=settings.max_correction_loops)

    # ── Step 9: Report ─────────────────────────────────────────────────────
    ctx = _run_report(ctx)

    logger.info("page_pipeline.done", page=page_name,
                score=ctx.report.overall_score if ctx.report else "n/a",
                issues=len(ctx.verified_issues))

    _write_artefacts(ctx)
    return _page_result(ctx)


# =============================================================================
# Internal step runners — each takes a PageContext, returns updated PageContext
# =============================================================================

def _run_simulations(ctx: PageContext, outer_state: dict) -> PageContext:
    """
    Run all personas in parallel using a thread pool.
    The rate_limiter semaphore caps concurrent Groq calls — no extra delays needed.
    """
    flat          = _ctx_to_flat(ctx)
    page_name     = Path(ctx.html_source_path).name
    all_results   = []
    
    # Initialize the shared async request pool for the Persona Swarm
    pool = PersonaAsyncRequestPool(
        keys=settings.persona_api_key.split(","),
        max_concurrent_per_key=getattr(settings, "llm_max_concurrent_calls", 5)
    )

    def _run_one(persona):
        persona_state = {
            **flat,
            **outer_state,
            "current_persona":    persona,
            "simulation_results": [],
            "patch_proposals":    [],
            "swarm_claims":       [],
            "persona_pool":       pool,
        }
        return _persona_node(persona_state)

    # UXAgent pattern: bound worker threads to avoid OS thread explosion.
    # With _ThreadLocalPlaywright each worker reuses its Playwright driver,
    # so 100 personas on 8 threads = 8 drivers instead of 100.
    max_workers = min(
        len(ctx.personas),
        getattr(settings, "max_num_personas", 8),
    )
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as tp:
        futures = {tp.submit(_run_one, p): p for p in ctx.personas}
        for future in as_completed(futures):
            persona = futures[future]
            try:
                result = future.result()
                sims   = result.get("simulation_results", [])
                all_results.extend(sims)
                logger.info("page_pipeline.persona_done",
                            page=page_name,
                            persona=persona.persona_id,
                            steps=sims[0].steps_taken if sims else 0,
                            issues=sum(len(s.issues) for s in sims))
            except Exception as e:
                logger.error("page_pipeline.persona_error",
                             persona=persona.persona_id, error=str(e))

    pool.stop()
    
    ctx = copy.copy(ctx)
    ctx.simulation_results = all_results
    return ctx


def _run_audit(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _audit_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_design_tokens(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _token_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_analysis(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _analysis_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_clustering(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _clustering_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_recommender_profiles(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _rec_profile_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_recommenders(ctx: PageContext) -> PageContext:
    """
    Run all recommender agents in parallel using a thread pool.
    Each agent gets a snapshot of swarm_claims at launch time
    (stigmergy — peers read existing claims, can't block on them).
    The rate_limiter semaphore handles Groq throttling.
    """
    flat        = _ctx_to_flat(ctx)
    all_claims  = list(ctx.swarm_claims)   # snapshot for all agents
    max_workers = getattr(settings, "llm_max_concurrent_calls", 5)

    # Build the full list of (profile, instance_index) pairs to run
    tasks: list[tuple] = []
    for profile in sorted(ctx.recommender_profiles, key=lambda p: p.priority):
        n = getattr(profile, "num_recommenders", 1)
        for i in range(n):
            active = (
                profile.model_copy(
                    update={"recommender_id": f"{profile.recommender_id}{chr(ord('a')+i)}"}
                ) if n > 1 else profile
            )
            tasks.append(active)

    def _run_one(active_profile):
        rec_state = {
            **flat,
            "current_recommender_profile": active_profile,
            "patch_proposals": [],
            "swarm_claims":    list(all_claims),   # snapshot, not live
        }
        return _recommender_node(rec_state)

    all_proposals = []
    # Cap workers to the configured concurrency limit (same as personas)
    worker_cap = min(len(tasks), max_workers,
                     getattr(settings, "llm_max_concurrent_calls", 5))
    with ThreadPoolExecutor(max_workers=max(1, worker_cap)) as pool:
        futures = {pool.submit(_run_one, t): t for t in tasks}
        for future in as_completed(futures):
            active = futures[future]
            try:
                result         = future.result()
                all_proposals += result.get("patch_proposals", [])
                all_claims    += result.get("swarm_claims",    [])
            except Exception as e:
                logger.error("page_pipeline.recommender_error",
                             recommender=active.recommender_id, error=str(e))

    ctx = copy.copy(ctx)
    ctx.patch_proposals = all_proposals
    ctx.swarm_claims    = all_claims
    return ctx


def _run_conflict_resolver(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _conflict_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_patch_applicator(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _patch_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_verification(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _verification_node(flat)
    return _flat_to_ctx(ctx, result)


def _run_report(ctx: PageContext) -> PageContext:
    flat   = _ctx_to_flat(ctx)
    result = _report_node(flat)
    return _flat_to_ctx(ctx, result)


def _prepare_correction(ctx: PageContext, loop: int) -> PageContext:
    """Reset PageContext for a correction loop on the patched HTML."""
    failing_ids = {
        vr.persona_id
        for vr in ctx.verification_results
        if vr.issues_remaining or vr.new_issues_introduced
    }
    correction_personas = (
        [p for p in ctx.personas if p.persona_id in failing_ids]
        or list(ctx.personas)
    )

    patched = ctx.patched_html_content or ctx.html_content
    stem    = Path(ctx.html_source_path).stem
    tmp     = tempfile.NamedTemporaryFile(
        mode="w", suffix=f"__patched_loop{loop}.html",
        prefix=f"ui_eval__{stem}__", delete=False, encoding="utf-8",
    )
    tmp.write(patched); tmp.flush(); tmp.close()

    logger.info("correction_loop.prepared",
                page=Path(ctx.html_source_path).name,
                loop=loop, personas=len(correction_personas),
                patched_path=tmp.name)

    return PageContext(
        html_source_path      = tmp.name,
        original_html_path    = ctx.original_html_path,
        html_content          = patched,
        ui_context            = ctx.ui_context,
        storage_seed          = ctx.storage_seed,
        ui_analysis           = ctx.ui_analysis,
        personas              = correction_personas,
        correction_loop_count = loop,
    )


# =============================================================================
# Output helpers
# =============================================================================

def _page_result(ctx: PageContext) -> dict:
    """
    Return dict that page_pipeline_node writes to shared state.
    current_page_context is intentionally NOT written back — it is injected
    per-branch by Send() and must never be written by parallel branches
    (plain field, not Annotated, so concurrent writes raise InvalidUpdateError).
    """
    return {
        "page_contexts": [ctx],
        "reports":       [ctx.report] if ctx.report else [],
    }


def _write_artefacts(ctx: PageContext) -> None:
    """Write all pipeline artefacts for one page to outputs/<stem>/."""
    output_root = Path(settings.output_dir)
    stem        = Path(ctx.html_source_path).stem
    page_dir    = output_root / stem
    page_dir.mkdir(parents=True, exist_ok=True)

    def _save(name: str, obj) -> None:
        if obj is None or (isinstance(obj, list) and not obj):
            return
        try:
            path = page_dir / name
            if hasattr(obj, "model_dump_json"):
                path.write_text(obj.model_dump_json(indent=2),
                                encoding="utf-8")
            elif isinstance(obj, list):
                items = [i.model_dump(mode="json") if hasattr(i, "model_dump") else i
                         for i in obj]
                path.write_text(json.dumps(items, indent=2, default=str),
                                encoding="utf-8")
            else:
                path.write_text(json.dumps(obj, indent=2, default=str),
                                encoding="utf-8")
        except Exception as e:
            logger.warning("artefacts.save_failed", file=name, error=str(e))

    _save("simulation_results.json",   ctx.simulation_results)
    _save("audit_results.json",        ctx.audit_results)
    _save("design_tokens.json",        ctx.design_tokens)
    _save("trace_verifications.json",  ctx.trace_verifications)
    _save("verified_issues.json",      ctx.verified_issues)
    _save("issue_clusters.json",       ctx.issue_clusters)
    _save("patch_proposals.json",      ctx.patch_proposals)
    _save("unified_patches.json",      ctx.unified_patch_set)
    _save("verification_results.json", ctx.verification_results)

    if ctx.patched_html_content:
        (page_dir / "patched.html").write_text(
            ctx.patched_html_content, encoding="utf-8")
    if ctx.report:
        (page_dir / "diagnostic_report.json").write_text(
            ctx.report.model_dump_json(indent=2),
            encoding="utf-8")

    logger.info("artefacts.written",
                page=Path(ctx.html_source_path).name, dir=str(page_dir))


# =============================================================================
# Build graph
# =============================================================================

def build_graph() -> Any:
    builder = StateGraph(GraphState)

    builder.add_node("supervisor_node",    supervisor_node)
    builder.add_node("page_pipeline_node", page_pipeline_node)

    builder.set_entry_point("supervisor_node")

    builder.add_conditional_edges(
        "supervisor_node",
        _fan_out_pages,
        {END: END},
    )

    builder.add_edge("page_pipeline_node", END)

    return builder.compile()


# =============================================================================
# Singleton + public API
# =============================================================================

_graph: Any = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_evaluation(
    pages: list[dict],
    used_persona_names:       list | None = None,
    used_persona_goals:       list | None = None,
    used_persona_constraints: list | None = None,
) -> dict:
    """
    Run the full MAS pipeline on one or more HTML pages.

    Pages are processed in parallel (one LangGraph branch per page).
    Personas within each page run sequentially with rate-limit delays.

    Args:
        pages: list of {"html_path": str, "ui_context": str (optional)}

    Returns:
        Final state dict.
        state["reports"] → list[DiagnosticReport], one per page.
    """
    setup_logging(log_level=settings.log_level, log_format=settings.log_format)

    initial = make_initial_state(
        pages=pages,
        used_persona_names=used_persona_names,
        used_persona_goals=used_persona_goals,
        used_persona_constraints=used_persona_constraints,
    )

    logger.info("run_evaluation.start", pages=len(pages))
    try:
        result  = _get_graph().invoke(initial)
        reports = result.get("reports", [])
        logger.info("run_evaluation.done", reports=len(reports))
        return result
    finally:
        # Clean up the shared Chromium browser process
        shutdown_shared_browser()