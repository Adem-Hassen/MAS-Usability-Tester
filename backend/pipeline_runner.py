# backend/pipeline_runner.py
"""
Bridges the FastAPI session to the MAS evaluation pipeline.

Runs in a background thread (via asyncio.to_thread) so it does not
block the FastAPI event loop. Emits SSE events at every major step.

If the MAS system is not installed / importable, a simulation mode
is used so the frontend can still be developed and demonstrated.
"""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime
from pathlib import Path

from backend.session_store import Session, SessionStatus, EventKind, SessionStore

# ---------------------------------------------------------------------------
# Try to import the real MAS system
# ---------------------------------------------------------------------------
import os
import sys
import logging
import traceback
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).parent.parent))

from monitoring.logger import get_logger
logger = get_logger(__name__)

try:
    from core.graph import run_evaluation
    from config.settings import settings
    MAS_AVAILABLE = True
except Exception as e:
    MAS_AVAILABLE = False
    logger.error(f"FATAL: The  MAS core failed to load. Error: {e}")
    logger.error(traceback.format_exc())


# ---------------------------------------------------------------------------
# Public entry point (called from FastAPI background task)
# ---------------------------------------------------------------------------

async def run_pipeline_async(session: Session, store: SessionStore) -> None:
    """Async wrapper — runs the blocking pipeline in a thread pool."""
    try:
        await asyncio.to_thread(_run_pipeline_sync, session, store)
    except asyncio.CancelledError:
        logger.info(f"Pipeline session {session.session_id} cancelled.")
        session.status = SessionStatus.FAILED
        session.error = "Pipeline was cancelled by a new request."
        session.finished_at = datetime.utcnow()
        store.emit(session.session_id, EventKind.ERROR,
                   stage="pipeline", message="Evaluation cancelled.")
        # Ensure we re-raise so the task finishes as cancelled
        raise
    except Exception as e:
        session.status  = SessionStatus.FAILED
        session.error   = str(e)
        session.finished_at = datetime.utcnow()
        store.emit(session.session_id, EventKind.ERROR,
                   stage="pipeline", message=str(e),
                   traceback=traceback.format_exc())
    finally:
        store.unregister_task(session.session_id)


# ---------------------------------------------------------------------------
# Synchronous pipeline (runs in thread)
# ---------------------------------------------------------------------------

def _run_pipeline_sync(session: Session, store: SessionStore) -> None:
    emit = lambda kind, **kw: store.emit(session.session_id, kind, **kw)

    total_pages = len(session.input_paths)
    all_results = []

    # ── V1 structured event: pipeline_start ────────────────────────────
    _model = ""
    try:
        from config.settings import settings as _s
        _model = _s.supervisor_llm_model
    except Exception:
        pass
    emit(EventKind.PIPELINE_START,
         job_id=session.session_id,
         file_count=total_pages,
         model=_model)

    # Legacy events
    emit(EventKind.LOG, level="info",
         message=f"Starting evaluation of {total_pages} page(s)")
    emit(EventKind.PROGRESS, value=2, label="Initialising pipeline")

    if MAS_AVAILABLE:
        _run_real_pipeline(session, store, emit, total_pages, all_results)
    else:
        if os.getenv("ALLOW_SIMULATION_FALLBACK", "false").lower() == "true":
            emit(EventKind.LOG, level="warning", message="MAS unavailable. Running in Simulation Mode.")
            _run_simulation(session, store, emit, total_pages, all_results)
        else:
            msg = "MAS pipeline is not available. Please check backend logs for import errors."
            logger.error(msg)
            raise RuntimeError(msg)

    # ── Build combined results object ─────────────────────────────────    # total_issues and total_patches are derived from the aggregated reports
    total_issues  = 0
    total_patches = 0
    for r in all_results:
        # r is a PageContext object
        if hasattr(r, "report") and r.report:
            total_issues  += r.report.total_issues_found
            total_patches += r.report.total_patches_applied
        elif isinstance(r, dict):
            # Fallback for dict-based results
            total_issues  += r.get("total_issues", 0)
            total_patches += r.get("total_patches", 0)

    total_pages = len(session.input_paths)

    # Calculate aggregates
    total_score = sum(
        r["overall_score"] for r in all_results 
        if isinstance(r, dict) and "overall_score" in r
    )
    score_avg = round(total_score / len(all_results), 1) if all_results else 0

    session.results = {
        "session_id":     session.session_id,
        "pages_total":    total_pages,
        "pages_done":     session.pages_done,
        "pages":          all_results,
        "score_avg":      score_avg,
        "issues_total":   total_issues,
        "patches_total":  total_patches,
        "fix_rate":       round((total_patches / total_issues * 100), 1) if total_issues > 0 else 0,
        "finished_at":    session.finished_at.isoformat() if session.finished_at else None,
    }

    # Save results to disk for recovery
    try:
        (session.output_dir / "results.json").write_text(
            json.dumps(session.results, indent=2, default=str), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"Failed to save results.json: {e}")

    # ── Generate PDF ──────────────────────────────────────────────────
    emit(EventKind.STEP, step="pdf_generation", status="running",
         label="Generating PDF report")
    try:
        _generate_pdf(session, all_results)
        emit(EventKind.STEP, step="pdf_generation", status="done",
             label="PDF report ready")
    except Exception as e:
        emit(EventKind.LOG, level="warning",
             message=f"PDF generation failed: {e}")

    session.status      = SessionStatus.DONE
    session.finished_at = datetime.utcnow()
    session.progress    = 100

    # Persist results to DB so API endpoints can retrieve them
    store.save_results(session.session_id, session.results)

    # ── V1 structured event: pipeline_complete ─────────────────────────
    has_pdf = (session.output_dir / "report.pdf").exists()
    emit(EventKind.PIPELINE_COMPLETE,
         job_id=session.session_id,
         issues_found=total_issues,
         patches_applied=total_patches,
         report_url=f"/api/v1/evaluate/{session.session_id}/report" if has_pdf else "",
         download_url=f"/api/v1/evaluate/{session.session_id}/download")

    # Legacy events
    emit(EventKind.PROGRESS, value=100, label="Complete")
    emit(EventKind.DONE,
         pages_done=session.pages_done,
         has_pdf=has_pdf)


# ---------------------------------------------------------------------------
# Real MAS pipeline
# ---------------------------------------------------------------------------

def _run_real_pipeline(session, store, emit, total_pages, all_results):
    import logging as _logging

    pages = [
        {
            "html_path":  str(p.resolve()),
            "ui_context": _infer_context(p),
        }
        for p in session.input_paths
    ]

    emit(EventKind.STEP, step="supervisor", status="running",
         pages_total=total_pages,
         label=f"Running evaluation on {total_pages} page(s)")
    emit(EventKind.PROGRESS, value=5,
         label=f"Supervisor analysing {total_pages} page(s)")

    # ── Subscribe EventBus to SSE emitter ──
    from core.event_bus import EventBus
    bus = EventBus.get()

    import threading

    # Map structlog event names → frontend step IDs + progress values
    _STEP_MAP = {
        "graph.supervisor_node.start":  ("supervisor",   "running", 5,  "Analysing UI…"),
        "graph.supervisor_node.done":   ("supervisor",   "done",    12, "UI analysis complete"),
        "supervisor.start":             ("supervisor",   "running", 5,  "Analysing UI structure…"),
        "fan_out_pages.sending":        ("supervisor",   "done",    15, "Starting page evaluations…"),
        "page_pipeline.start":          ("personas",     "running", 18, "Running persona simulations…"),
        "page_pipeline.persona_done":   ("personas",     "running", 25, "Persona simulation in progress…"),
        "page_pipeline.no_issues":      ("report",       "running", 60, "No issues found — generating report…"),
        "page_pipeline.verification_passed":   ("verification", "done", 55, "Verification passed"),
        "page_pipeline.verification_failed":   ("verification", "done", 50, "Verification — needs correction"),
        "page_pipeline.done":           ("report",       "done",    65, "Page evaluation complete"),
        "correction_loop.prepared":     ("verification", "running", 50, "Running correction loop…"),
        "recommender.start":            ("recommender",  "running", 38, "Generating patches…"),
        "recommender.proposal_complete": ("recommender", "running", 42, "Patch generated"),
        "recommender.proposal_failed":   ("recommender", "running", 42, "Patch generation failed"),
        "persona.start":                ("personas",     "running", 18, "Persona started"),
        "persona.action":               ("personas",     "running", 20, "Persona action"),
    }
    # Map internal function names to step IDs (from the _run_* calls in graph.py)
    _FUNC_STEP_MAP = {
        "analysis_node":        ("personas",     "done",    28, "Trace analysis complete"),
        "clustering_node":      ("clustering",   "running", 30, "Clustering issues…"),
        "cluster_engine":       ("clustering",   "done",    35, "Issue clustering complete"),
        "recommender_node":     ("recommender",  "running", 38, "Generating patches…"),
        "conflict_resolver":    ("resolver",     "running", 45, "Resolving conflicts…"),
        "patch_applicator":     ("applicator",   "running", 50, "Applying patches…"),
        "verification_node":    ("verification", "running", 55, "Verifying fixes…"),
        "report_generator":     ("report",       "running", 60, "Generating report…"),
    }

    _last_step = [None]

    def _emit_step(step_id, status, prog, label):
        _last_step[0] = step_id
        emit(EventKind.STEP, step=step_id, status=status,
             pages_total=total_pages, label=label)
        emit(EventKind.PROGRESS, value=prog, label=label)

    def _emit_v1_event(event_key, payload):
        def _save_screenshot(b64_data: str, prefix: str) -> str:
            if not b64_data:
                return ""
            import uuid
            import base64
            filename = f"{prefix}_{uuid.uuid4().hex[:8]}.jpeg"
            path = session.output_dir / filename
            try:
                path.write_bytes(base64.b64decode(b64_data))
                return f"/api/v1/evaluate/{session.session_id}/screenshots/{filename}"
            except Exception:
                return ""

        if event_key == "graph.supervisor_node.done":
            emit(EventKind.SUPERVISOR_ANALYSIS, summary="UI analysis complete")
        elif event_key == "page_pipeline.start":
            emit(EventKind.PERSONA_START, persona_id="batch", persona_name="All personas")
        elif event_key == "page_pipeline.persona_done":
            emit(EventKind.PERSONA_COMPLETE, persona_id="batch", issues_found=0)
        elif event_key == "persona.start":
            scr_url = _save_screenshot(payload.get("screenshot"), f"start_{payload.get('persona_id', 'unknown')}")
            emit(EventKind.PERSONA_START,
                 persona_id=payload.get("persona_id"), 
                 persona_name=payload.get("persona_name"), 
                 screenshot=scr_url)
        elif event_key == "persona.action":
            scr_url = _save_screenshot(payload.get("screenshot"), f"action_{payload.get('persona_id', 'unknown')}")
            emit(EventKind.PERSONA_ACTION,
                 persona_id=payload.get("persona_id"), 
                 persona_name=payload.get("persona_name"),
                 action_type=payload.get("action_type"), 
                 selector=payload.get("selector"), 
                 result=payload.get("result"),
                 screenshot=scr_url,
                 bounding_box=payload.get("bounding_box"))
        elif event_key in ("clustering_node", "cluster_engine"):
            if "clustering_node" == event_key:
                emit(EventKind.CLUSTERING_START, raw_issue_count=0)
            else:
                emit(EventKind.CLUSTERING_COMPLETE, cluster_count=0, duplicate_count=0)
        elif event_key == "recommender.start" or event_key == "recommender_node":
            emit(EventKind.RECOMMENDER_START, recommender_id="batch", cluster_ids=[])
        elif event_key == "recommender.proposal_complete":
            emit(EventKind.RECOMMENDER_PATCH, status="done", message="Patch generated")
        elif event_key == "recommender.proposal_failed":
            emit(EventKind.RECOMMENDER_PATCH, status="error", message="Patch generation failed")
        elif event_key == "conflict_resolver":
            emit(EventKind.CONFLICT_RESOLVED, resolution_strategy="llm")
        elif event_key == "patch_applicator":
            # PATCH_APPLIED is now emitted from _extract_results with the real count.
            # We only emit a progress step here so the UI shows "Applying patches…".
            emit(EventKind.STEP, step="applicator", status="running",
                 label="Applying patches…")

    def _bus_handler(event_type: str, payload: dict):
        if event_type == "log_event":
            msg = payload.get("event", "")
            level = payload.get("level", "info")
            
            # Remove ANSI colors if any
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            clean_text = ansi_escape.sub('', msg)
            
            emit(EventKind.LOG, level=level, message=clean_text)

            for event_prefix, (step_id, status, prog, label) in _STEP_MAP.items():
                if event_prefix in msg:
                    _emit_step(step_id, status, prog, label)
                    _emit_v1_event(event_prefix, payload)
                    return

            for func_key, (step_id, status, prog, label) in _FUNC_STEP_MAP.items():
                if func_key in msg:
                    if step_id != _last_step[0]:
                        _emit_step(step_id, status, prog, label)
                        _emit_v1_event(func_key, payload)
                    return
        else:
            try:
                kind = EventKind(event_type)
                emit(kind, **payload)
            except ValueError:
                pass

    bus.subscribe(_bus_handler)

    # Heartbeat thread: send keepalive progress in case no log events arrive
    _pipeline_done = threading.Event()

    def _heartbeat():
        while not _pipeline_done.wait(timeout=20):
            # Omit value entirely so frontend doesn't coalesce nullish to 0
            emit(EventKind.PROGRESS, label="Pipeline running…")

    heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
    heartbeat_thread.start()

    try:
        # We no longer need to redirect sys.stdout
        state = run_evaluation(pages=pages)
    except Exception as e:
        _pipeline_done.set()
        emit(EventKind.LOG, level="error",
             message=f"Pipeline failed: {e}")
        for p in pages:
            stem = Path(p["html_path"]).stem
            all_results.append({"page": stem, "error": str(e)})
        return
    finally:
        _pipeline_done.set()
        heartbeat_thread.join(timeout=2)
        bus.unsubscribe_all()

    emit(EventKind.STEP, step="supervisor", status="done",
         pages_total=total_pages,
         label="Pipeline execution complete")
    emit(EventKind.PROGRESS, value=70, label="Processing results")

    # ── Extract results from pipeline state ──
    # state["page_contexts"] is list[PageContext], state["reports"] is list[DiagnosticReport]
    page_contexts = state.get("page_contexts", [])
    reports       = state.get("reports", [])

    # Build a lookup from source path stem to PageContext and Report
    ctx_by_stem = {}
    for ctx in page_contexts:
        base_path = getattr(ctx, "original_html_path", "") or ctx.html_source_path
        stem = Path(base_path).stem
        # Correction loop creates temp file names — map back to original
        # by matching against the input pages list
        for p in pages:
            if Path(p["html_path"]).stem in stem:
                stem = Path(p["html_path"]).stem
                break
        ctx_by_stem[stem] = ctx

    report_by_stem = {}
    for rpt in reports:
        if rpt is None:
            continue
        # If rpt is a dictionary (can happen with Pydantic serialization)
        if isinstance(rpt, dict):
            base_path = rpt.get("original_html_path", "") or rpt.get("html_source_path", "")
        else:
            base_path = getattr(rpt, "original_html_path", "") or rpt.html_source_path
            
        stem = Path(base_path).stem
        for p in pages:
            if Path(p["html_path"]).stem in stem:
                stem = Path(p["html_path"]).stem
                break
        report_by_stem[stem] = rpt

    for idx, page in enumerate(pages):
        stem     = Path(page["html_path"]).stem
        page_num = idx + 1
        ctx      = ctx_by_stem.get(stem)
        report   = report_by_stem.get(stem)
        
        logger.info("pipeline.extract_results", stem=stem, 
                    has_ctx=bool(ctx), has_report=bool(report),
                    issues=len(ctx.verified_issues) if ctx else 0)

        # Emit issues from page context
        if ctx:
            for cluster in (ctx.issue_clusters or []):
                for issue in getattr(cluster, "issues", []):
                    issue_d = issue.model_dump() if hasattr(issue, "model_dump") else issue
                    emit(EventKind.ISSUE,
                         page=stem,
                         issue_id=issue.issue_id,
                         title=issue.title,
                         severity=str(issue.severity),
                         category=str(issue.category),
                         target=issue.affected_element or "",
                         description=issue.description)

            # Emit patches
            ups = ctx.unified_patch_set
            if ups and hasattr(ups, "patches"):
                for patch in ups.patches:
                    patch_d = patch.model_dump() if hasattr(patch, "model_dump") else patch
                    emit(EventKind.PATCH,
                         page=stem,
                         patch_id=patch.resolved_patch_id,
                         target=patch.target_element,
                         description=patch.description,
                         patch_type=str(patch.patch_type))

            # Save patched HTML
            patched = ctx.patched_html_content or ctx.html_content
            out_file = session.output_dir / f"{stem}_fixed.html"
            if patched:
                out_file.write_text(patched, encoding="utf-8")

            # Emit real patch-applied count (replaces the hardcoded 0 from _emit_v1_event)
            applied_count = getattr(ctx, 'total_patches_applied', 0) or 0
            emit(EventKind.PATCH_APPLIED,
                 file_name=f"{stem}.html",
                 patch_count=applied_count)
            emit(EventKind.STEP, step="applicator", status="done",
                 page=stem, label=f"Applied {applied_count} patches")

        # Save report JSON
        if report:
            rpt_d = report.model_dump(mode="json") if hasattr(report, "model_dump") \
                    else report
            (session.output_dir / f"{stem}_report.json").write_text(
                json.dumps(rpt_d, indent=2, default=str), encoding="utf-8")

            all_results.append({
                "page":            stem,
                "original_file":   Path(page["html_path"]).name,
                "fixed_file":      f"{stem}_fixed.html" if ctx and (ctx.patched_html_content or ctx.html_content) else None,
                "report_file":     f"{stem}_report.json",
                "overall_score":   report.overall_score,
                "total_issues":    report.total_issues_found,
                "patches_applied": report.total_patches_applied,
                "summary":         report.executive_summary,
                "recommendations": report.top_recommendations,
            })
        else:
            all_results.append({"page": stem, "error": "No report generated"})

        session.pages_done += 1
        emit(EventKind.STEP, step="complete", status="done", page=stem,
             page_num=page_num, pages_total=total_pages,
             label=f"[{page_num}/{total_pages}] {stem} complete")
        emit(EventKind.PROGRESS,
             value=int(((idx + 1) / total_pages) * 90),
             label=f"Completed {page_num}/{total_pages} pages")

    session.finished_at = datetime.utcnow()


# ---------------------------------------------------------------------------
# Simulation mode (when MAS not installed)
# ---------------------------------------------------------------------------

def _run_simulation(session, store, emit, total_pages, all_results):
    import time, random

    steps = [
        ("supervisor",   "Supervisor analysing UI",    8),
        ("personas",     "Running persona simulations", 20),
        ("clustering",   "Clustering issues",           5),
        ("recommender",  "Generating patch proposals",  12),
        ("resolver",     "Resolving conflicts",         5),
        ("applicator",   "Applying patches",            5),
        ("verification", "Verifying fixes",             5),
        ("report",       "Generating report",           5),
    ]

    FAKE_ISSUES = [
        ("Missing form label", "high", "accessibility",
         "Input field #email has no associated <label> element."),
        ("Insufficient color contrast", "high", "accessibility",
         "Text #subtitle has contrast ratio 2.1:1 (required ≥ 4.5:1)."),
        ("No focus indicator", "medium", "accessibility",
         "Interactive elements have outline:none — keyboard users cannot see focus."),
        ("Custom checkbox inaccessible", "medium", "accessibility",
         "Checkbox implemented as <div> — not reachable by keyboard."),
        ("Missing alt text", "low", "accessibility",
         "Decorative image lacks alt='' attribute."),
    ]

    for idx, page_path in enumerate(session.input_paths):
        stem     = page_path.stem
        page_num = idx + 1
        base     = int((idx / total_pages) * 88)

        emit(EventKind.LOG, level="info",
             message=f"Processing page {page_num}/{total_pages}: {stem}")

        step_share = 88 // total_pages // len(steps)

        for s_idx, (step_id, label, _) in enumerate(steps):
            emit(EventKind.STEP, step=step_id, status="running",
                 page=stem, page_num=page_num, pages_total=total_pages,
                 label=f"[{page_num}/{total_pages}] {label}")
            time.sleep(random.uniform(0.3, 0.8))

            if step_id == "clustering":
                n_issues = random.randint(2, 4)
                for title, sev, cat, desc in random.sample(FAKE_ISSUES, n_issues):
                    emit(EventKind.ISSUE, page=stem,
                         issue_id=f"{stem}_issue_{random.randint(1000,9999)}",
                         title=title, severity=sev, category=cat, description=desc)

            if step_id == "applicator":
                emit(EventKind.PATCH, page=stem,
                     patch_id=f"{stem}_patch_1",
                     target="#email",
                     description="Added <label for='email'>Email address</label>",
                     patch_type="html_attribute")
                emit(EventKind.PATCH, page=stem,
                     patch_id=f"{stem}_patch_2",
                     target=".btn-submit",
                     description="Added aria-label and focus ring CSS",
                     patch_type="css_snippet")

            emit(EventKind.STEP, step=step_id, status="done",
                 page=stem, label=f"[{page_num}/{total_pages}] {label}")
            prog = base + int(((s_idx + 1) / len(steps)) * (88 // total_pages))
            emit(EventKind.PROGRESS, value=min(prog, 90), label=label)

        # Write fake fixed HTML
        original_html = page_path.read_text(encoding="utf-8", errors="replace")
        fixed_html = original_html.replace(
            "<head>",
            "<head>\n<!-- Nexus Accessibility Fixes Applied -->"
        )
        out_file = session.output_dir / f"{stem}_fixed.html"
        out_file.write_text(fixed_html, encoding="utf-8")

        score = round(random.uniform(6.5, 9.2), 1)
        all_results.append({
            "page":            stem,
            "original_file":   page_path.name,
            "fixed_file":      out_file.name,
            "report_file":     None,
            "overall_score":   score,
            "total_issues":    random.randint(3, 8),
            "patches_applied": random.randint(2, 5),
            "summary":         (
                f"The {stem} page was evaluated across 2 personas. "
                f"Several accessibility issues were identified and patched, "
                f"raising the overall score to {score}/10."
            ),
            "recommendations": [
                "Add visible labels to all form inputs",
                "Ensure colour contrast meets WCAG AA (4.5:1 minimum)",
                "Remove outline:none from interactive elements",
                "Replace custom div-based controls with native HTML elements",
            ],
        })

        session.pages_done += 1
        emit(EventKind.STEP, step="complete", status="done",
             page=stem, page_num=page_num, pages_total=total_pages,
             label=f"[{page_num}/{total_pages}] {stem} complete")

    session.finished_at = datetime.utcnow()


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def _generate_pdf(session: Session, all_results: list[dict]) -> None:
    """Generate a PDF report using ReportLab (or fpdf2 as fallback)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        _generate_pdf_reportlab(session, all_results)
    except ImportError:
        try:
            from fpdf import FPDF
            _generate_pdf_fpdf(session, all_results)
        except ImportError:
            # Fallback: write a plain-text PDF placeholder
            _generate_pdf_text(session, all_results)


def _generate_pdf_reportlab(session: Session, all_results: list) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )

    pdf_path = session.output_dir / "report.pdf"
    doc      = SimpleDocTemplate(str(pdf_path), pagesize=A4,
                                  leftMargin=2*cm, rightMargin=2*cm,
                                  topMargin=2*cm, bottomMargin=2*cm)
    styles   = getSampleStyleSheet()

    title_style = ParagraphStyle("Title", parent=styles["Heading1"],
                                  fontSize=22, textColor=colors.HexColor("#1a1a18"),
                                  spaceAfter=6)
    h2_style    = ParagraphStyle("H2", parent=styles["Heading2"],
                                  fontSize=14, textColor=colors.HexColor("#2d4a3e"),
                                  spaceAfter=4, spaceBefore=12)
    body_style  = ParagraphStyle("Body", parent=styles["Normal"],
                                  fontSize=10, leading=15,
                                  textColor=colors.HexColor("#3d3d3a"))
    meta_style  = ParagraphStyle("Meta", parent=styles["Normal"],
                                  fontSize=9, textColor=colors.HexColor("#7a7770"))

    story = [
        Paragraph("Nexus Accessibility Report", title_style),
        Paragraph(
            f"Session: {session.session_id} · "
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            meta_style
        ),
        Spacer(1, 0.4*cm),
        HRFlowable(width="100%", color=colors.HexColor("#e8e2d8")),
        Spacer(1, 0.4*cm),
    ]

    for res in all_results:
        page = res.get("page", "unknown")
        story.append(Paragraph(f"Page: {page}", h2_style))

        if res.get("error"):
            story.append(Paragraph(f"⚠ Error: {res['error']}", body_style))
        else:
            score   = res.get("overall_score", "n/a")
            issues  = res.get("total_issues", 0)
            patches = res.get("patches_applied", 0)

            tdata = [
                ["Overall Score", str(score) + " / 10"],
                ["Issues Found",  str(issues)],
                ["Patches Applied", str(patches)],
            ]
            t = Table(tdata, colWidths=[5*cm, 10*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f2ee")),
                ("TEXTCOLOR",  (0, 0), (0, -1), colors.HexColor("#7a7770")),
                ("FONTSIZE",   (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                 [colors.white, colors.HexColor("#faf9f7")]),
                ("BOX",  (0, 0), (-1, -1), 0.5, colors.HexColor("#e8e2d8")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e8e2d8")),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.3*cm))

            if res.get("summary"):
                story.append(Paragraph("Summary", ParagraphStyle(
                    "SH", parent=body_style, fontName="Helvetica-Bold")))
                story.append(Paragraph(res["summary"], body_style))
                story.append(Spacer(1, 0.2*cm))

            recs = res.get("recommendations", [])
            if recs:
                story.append(Paragraph("Top Recommendations", ParagraphStyle(
                    "SH", parent=body_style, fontName="Helvetica-Bold")))
                for i, r in enumerate(recs[:5], 1):
                    story.append(Paragraph(f"{i}. {r}", body_style))

        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", color=colors.HexColor("#e8e2d8")))
        story.append(Spacer(1, 0.3*cm))

    doc.build(story)


def _generate_pdf_fpdf(session: Session, all_results: list) -> None:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "Nexus Accessibility Report", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, f"Session: {session.session_id}", ln=True)
    pdf.ln(4)

    for res in all_results:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, f"Page: {res.get('page', 'unknown')}", ln=True)
        pdf.set_font("Helvetica", "", 10)
        if res.get("error"):
            pdf.cell(0, 6, f"Error: {res['error']}", ln=True)
        else:
            pdf.cell(0, 6, f"Score: {res.get('overall_score', 'n/a')} / 10", ln=True)
            pdf.cell(0, 6, f"Issues: {res.get('total_issues', 0)}  |  Patches: {res.get('patches_applied', 0)}", ln=True)
            if res.get("summary"):
                pdf.multi_cell(0, 5, res["summary"])
            pdf.ln(3)
            for rec in res.get("recommendations", [])[:5]:
                pdf.multi_cell(0, 5, f"• {rec}")
        pdf.ln(5)

    pdf.output(str(session.output_dir / "report.pdf"))


def _generate_pdf_text(session: Session, all_results: list) -> None:
    """Absolute fallback — plain text saved as .pdf (not a real PDF)."""
    lines = [
        "NEXUS ACCESSIBILITY REPORT",
        f"Session: {session.session_id}",
        f"Generated: {datetime.utcnow().isoformat()}",
        "=" * 60,
    ]
    for res in all_results:
        lines += [
            f"\nPage: {res.get('page', 'unknown')}",
            f"Score: {res.get('overall_score', 'n/a')} / 10",
            f"Issues: {res.get('total_issues', 0)}",
            f"Patches: {res.get('patches_applied', 0)}",
            res.get("summary", ""),
        ]
        for rec in res.get("recommendations", []):
            lines.append(f"  • {rec}")
    (session.output_dir / "report.pdf").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_context(path: Path) -> str:
    stem = path.stem.replace("_", " ").replace("-", " ").title()
    return f"{stem} — web UI"
