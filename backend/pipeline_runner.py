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
try:
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).parent.parent))
    from core.graph import run_evaluation
    from config.settings import settings
    MAS_AVAILABLE = True
except ImportError:
    MAS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public entry point (called from FastAPI background task)
# ---------------------------------------------------------------------------

async def run_pipeline_async(session: Session, store: SessionStore) -> None:
    """Async wrapper — runs the blocking pipeline in a thread pool."""
    try:
        await asyncio.to_thread(_run_pipeline_sync, session, store)
    except Exception as e:
        session.status  = SessionStatus.FAILED
        session.error   = str(e)
        session.finished_at = datetime.utcnow()
        store.emit(session.session_id, EventKind.ERROR,
                   message=str(e), trace=traceback.format_exc())


# ---------------------------------------------------------------------------
# Synchronous pipeline (runs in thread)
# ---------------------------------------------------------------------------

def _run_pipeline_sync(session: Session, store: SessionStore) -> None:
    emit = lambda kind, **kw: store.emit(session.session_id, kind, **kw)

    total_pages = len(session.input_paths)
    all_results = []

    emit(EventKind.LOG, level="info",
         message=f"Starting evaluation of {total_pages} page(s)")
    emit(EventKind.PROGRESS, value=2, label="Initialising pipeline")

    if MAS_AVAILABLE:
        _run_real_pipeline(session, store, emit, total_pages, all_results)
    else:
        _run_simulation(session, store, emit, total_pages, all_results)

    # ── Build combined results object ─────────────────────────────────
    session.results = {
        "session_id":  session.session_id,
        "pages_total": total_pages,
        "pages_done":  session.pages_done,
        "pages":       all_results,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
    }

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

    emit(EventKind.PROGRESS, value=100, label="Complete")
    emit(EventKind.DONE,
         pages_done=session.pages_done,
         has_pdf=(session.output_dir / "report.pdf").exists())


# ---------------------------------------------------------------------------
# Real MAS pipeline
# ---------------------------------------------------------------------------

def _run_real_pipeline(session, store, emit, total_pages, all_results):
    pages = [
        {
            "html_path":  str(p.resolve()),
            "ui_context": _infer_context(p),
        }
        for p in session.input_paths
    ]

    for idx, page in enumerate(pages):
        stem      = Path(page["html_path"]).stem
        page_num  = idx + 1
        base_prog = int((idx / total_pages) * 90)

        emit(EventKind.STEP, step="supervisor", status="running",
             page=stem, page_num=page_num, pages_total=total_pages,
             label=f"[{page_num}/{total_pages}] Analysing {stem}")
        emit(EventKind.PROGRESS, value=base_prog + 5,
             label=f"Supervisor analysing {stem}")

        try:
            state = run_evaluation(
                pages=pages
            )
        except Exception as e:
            emit(EventKind.LOG, level="error",
                 message=f"Pipeline failed for {stem}: {e}")
            all_results.append({"page": stem, "error": str(e)})
            continue

        report = state.get("report")

        # Emit issues
        for cluster in state.get("issue_clusters", []):
            for issue in cluster.get("issues", []) if isinstance(cluster, dict) \
                    else getattr(cluster, "issues", []):
                issue_d = issue if isinstance(issue, dict) else issue.model_dump()
                emit(EventKind.ISSUE,
                     page=stem,
                     issue_id=issue_d.get("issue_id"),
                     title=issue_d.get("title"),
                     severity=str(issue_d.get("severity", "medium")),
                     category=str(issue_d.get("category", "usability")),
                     description=issue_d.get("description", ""))

        # Emit patches
        ups = state.get("unified_patch_set")
        patches = ups.patches if ups and hasattr(ups, "patches") else \
                  ups.get("patches", []) if isinstance(ups, dict) else []
        for patch in patches:
            patch_d = patch if isinstance(patch, dict) else patch.model_dump()
            emit(EventKind.PATCH,
                 page=stem,
                 patch_id=patch_d.get("resolved_patch_id"),
                 target=patch_d.get("target_element"),
                 description=patch_d.get("description", ""),
                 patch_type=patch_d.get("patch_type", "html_attribute"))

        # Save patched HTML
        patched = state.get("patched_html_content") or state.get("html_content", "")
        out_file = session.output_dir / f"{stem}_fixed.html"
        if patched:
            out_file.write_text(patched, encoding="utf-8")

        # Save report JSON
        if report:
            rpt_d = report.model_dump(mode="json") if hasattr(report, "model_dump") \
                    else report
            (session.output_dir / f"{stem}_report.json").write_text(
                json.dumps(rpt_d, indent=2, default=str), encoding="utf-8")

            all_results.append({
                "page":            stem,
                "fixed_file":      out_file.name if patched else None,
                "report_file":     f"{stem}_report.json",
                "overall_score":   getattr(report, "overall_score", rpt_d.get("overall_score")),
                "total_issues":    getattr(report, "total_issues_found", rpt_d.get("total_issues_found", 0)),
                "patches_applied": getattr(report, "total_patches_applied", rpt_d.get("total_patches_applied", 0)),
                "summary":         getattr(report, "executive_summary", rpt_d.get("executive_summary", "")),
                "recommendations": getattr(report, "top_recommendations", rpt_d.get("top_recommendations", [])),
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
