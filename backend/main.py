# backend/main.py
"""
MAS Usability Tester — FastAPI Backend

Endpoints (v1 — primary):
  POST /api/v1/evaluate                    — upload HTML files + start pipeline
  GET  /api/v1/evaluate/{job_id}/stream    — SSE stream (Last-Event-ID support)
  GET  /api/v1/evaluate/{job_id}/issues    — clustered issues JSON
  GET  /api/v1/evaluate/{job_id}/report    — PDF download
  GET  /api/v1/evaluate/{job_id}/download  — ZIP of patched files
  GET  /api/v1/health                      — health check

Legacy (kept for backward compatibility):
  POST /api/sessions                       — create session
  POST /api/sessions/{id}/run              — trigger pipeline
  GET  /api/sessions/{id}/stream           — SSE stream
  GET  /api/sessions/{id}/results          — final results
  GET  /api/sessions/{id}/files/{filename} — download fixed HTML
  GET  /api/sessions/{id}/report.pdf       — PDF report
  GET  /api/sessions/{id}/status           — quick status poll
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

# ---------------------------------------------------------------------------
# Bootstrap project path so we can import the MAS system
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.session_store import SessionStore, Session, SessionStatus, EventKind
from backend.pipeline_runner import run_pipeline_async

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MAS Usability Tester",
    version="2.0.0",
    docs_url="/api/docs",
)

# CORS: configurable via env var, defaults to localhost dev servers
_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SessionStore()

# ===========================================================================
# V1 API — Target Spec Endpoints
# ===========================================================================

@app.post("/api/v1/evaluate", status_code=201)
async def evaluate(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Single-step: upload HTML files and immediately start the evaluation pipeline.
    Returns { job_id, file_count, status: "queued" }.
    """
    if not files:
        raise HTTPException(400, "At least one HTML file is required.")
    if len(files) > 5:
        raise HTTPException(400, "Maximum 5 HTML files allowed per session.")

    for f in files:
        if not f.filename.endswith(".html"):
            raise HTTPException(400, f"File '{f.filename}' is not an HTML file.")
        if f.size and f.size > 5 * 1024 * 1024:
            raise HTTPException(400, f"File '{f.filename}' exceeds 5 MB limit.")

    job_id = uuid.uuid4().hex[:12]
    session = await store.create(job_id, files)

    # Immediately start the pipeline
    session.status = SessionStatus.RUNNING
    session.started_at = datetime.utcnow()
    background_tasks.add_task(run_pipeline_async, session, store)

    return {
        "job_id": job_id,
        "file_count": len(files),
        "status": "queued",
    }


@app.get("/api/v1/evaluate/{job_id}/stream")
async def stream_evaluate(job_id: str, request: Request):
    """
    SSE stream with Last-Event-ID reconnection support.
    Emits structured events with `id:` field for each event.
    """
    _get_session(job_id)

    # Parse Last-Event-ID for reconnection
    last_event_id = -1
    raw_id = request.headers.get("Last-Event-ID", request.headers.get("last-event-id", ""))
    if raw_id:
        try:
            last_event_id = int(raw_id)
        except ValueError:
            pass

    async def event_generator() -> AsyncGenerator[str, None]:
        q: asyncio.Queue = asyncio.Queue()
        store._queues.setdefault(job_id, []).append(q)

        try:
            # Replay buffered events (for reconnect — only events after last_event_id)
            for ev in store.get_events(job_id, after_id=last_event_id):
                yield _sse_with_id(ev)
                if store.is_terminal(ev):
                    return

            # Listen for live events with periodic keepalive
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse_with_id(event)
                    if store.is_terminal(event):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                store._queues[job_id].remove(q)
            except (KeyError, ValueError):
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/v1/evaluate/{job_id}/issues")
async def get_issues(job_id: str):
    """Return clustered issues for a completed job."""
    session = _get_session(job_id)
    results = session.results or {}
    clusters = []

    for page_data in results.get("pages", []):
        page_name = page_data.get("page", "unknown")
        # Build clusters from stored issue events
        for ev in store.get_events(job_id):
            if ev.get("kind") == EventKind.ISSUE and ev.get("page") == page_name:
                clusters.append({
                    "cluster_id": ev.get("issue_id", ""),
                    "severity": ev.get("severity", "medium"),
                    "selector": ev.get("target", ""),
                    "description": ev.get("description", ""),
                    "personas": [],
                    "patch_applied": False,
                })

    return {"clusters": clusters}


@app.get("/api/v1/evaluate/{job_id}/report")
async def download_report_v1(job_id: str):
    """Download PDF report."""
    session = _get_session(job_id)
    if session.status != SessionStatus.DONE:
        raise HTTPException(425, "Processing not complete yet.")
    pdf_path = session.output_dir / "report.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF report not yet generated.")
    return FileResponse(pdf_path, filename=f"mas_report_{job_id}.pdf",
                        media_type="application/pdf")


@app.get("/api/v1/evaluate/{job_id}/download")
async def download_patched_zip(job_id: str):
    """Download ZIP of all patched HTML files."""
    session = _get_session(job_id)
    if session.status != SessionStatus.DONE:
        raise HTTPException(425, "Processing not complete yet.")

    # Collect all *_fixed.html files from output dir
    fixed_files = list(session.output_dir.glob("*_fixed.html"))
    if not fixed_files:
        raise HTTPException(404, "No patched files available.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in fixed_files:
            zf.write(f, f.name)
        # Include PDF if it exists
        pdf = session.output_dir / "report.pdf"
        if pdf.exists():
            zf.write(pdf, "report.pdf")

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="mas_patched_{job_id}.zip"',
        },
    )


@app.get("/api/v1/health")
async def health_v1():
    """Health check with model and token info."""
    model = ""
    try:
        from config.settings import settings
        model = settings.supervisor_llm_model
    except Exception:
        pass
    return {
        "status": "ok",
        "model": model,
        "tokens_remaining": 0,  # TODO: wire to rate_limiter TPM tracker
        "time": datetime.utcnow().isoformat(),
    }


# ===========================================================================
# Legacy API — Backward Compatibility
# ===========================================================================

@app.post("/api/sessions", status_code=201)
async def create_session(files: list[UploadFile] = File(...)):
    """Upload up to 5 HTML files and create an evaluation session."""
    if not files:
        raise HTTPException(400, "At least one HTML file is required.")
    if len(files) > 5:
        raise HTTPException(400, "Maximum 5 HTML files allowed per session.")

    for f in files:
        if not f.filename.endswith(".html"):
            raise HTTPException(400, f"File '{f.filename}' is not an HTML file.")
        if f.size and f.size > 5 * 1024 * 1024:
            raise HTTPException(400, f"File '{f.filename}' exceeds 5 MB limit.")

    session_id = uuid.uuid4().hex[:12]
    session = await store.create(session_id, files)
    return {
        "session_id": session_id,
        "files": [p.name for p in session.input_paths],
        "created_at": session.created_at.isoformat(),
    }


@app.post("/api/sessions/{session_id}/run", status_code=202)
async def run_session(session_id: str, background_tasks: BackgroundTasks):
    """Trigger the evaluation pipeline for a session."""
    session = _get_session(session_id)
    if session.status not in (SessionStatus.READY, SessionStatus.FAILED):
        raise HTTPException(409, f"Session is already {session.status.value}.")

    session.status = SessionStatus.RUNNING
    session.started_at = datetime.utcnow()
    background_tasks.add_task(run_pipeline_async, session, store)
    return {"session_id": session_id, "status": "running"}


@app.get("/api/sessions/{session_id}/stream")
async def stream_session(session_id: str, request: Request):
    """Server-Sent Events stream of real-time pipeline events (legacy)."""
    _get_session(session_id)

    last_event_id = -1
    raw_id = request.headers.get("Last-Event-ID", "")
    if raw_id:
        try:
            last_event_id = int(raw_id)
        except ValueError:
            pass

    async def event_generator() -> AsyncGenerator[str, None]:
        q: asyncio.Queue = asyncio.Queue()
        store._queues.setdefault(session_id, []).append(q)

        try:
            for ev in store.get_events(session_id, after_id=last_event_id):
                yield _sse_with_id(ev)
                if store.is_terminal(ev):
                    return

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    yield _sse_with_id(event)
                    if store.is_terminal(event):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                store._queues[session_id].remove(q)
            except (KeyError, ValueError):
                pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/sessions/{session_id}/status")
async def get_status(session_id: str):
    session = _get_session(session_id)
    return {
        "session_id": session_id,
        "status": session.status.value,
        "progress": session.progress,
        "pages_total": len(session.input_paths),
        "pages_done": session.pages_done,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
    }


@app.get("/api/sessions/{session_id}/results")
async def get_results(session_id: str):
    session = _get_session(session_id)
    if session.status != SessionStatus.DONE:
        raise HTTPException(425, "Processing not complete yet.")
    return session.results


@app.get("/api/sessions/{session_id}/files/{filename}")
async def download_fixed_file(session_id: str, filename: str):
    session = _get_session(session_id)
    if session.status != SessionStatus.DONE:
        raise HTTPException(425, "Processing not complete yet.")
    path = session.output_dir / filename
    if not path.exists():
        raise HTTPException(404, f"File '{filename}' not found.")
    return FileResponse(path, filename=filename, media_type="text/html")


@app.get("/api/sessions/{session_id}/report.pdf")
async def download_report(session_id: str):
    session = _get_session(session_id)
    if session.status != SessionStatus.DONE:
        raise HTTPException(425, "Processing not complete yet.")
    pdf_path = session.output_dir / "report.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF report not yet generated.")
    return FileResponse(pdf_path, filename=f"nexus_report_{session_id}.pdf",
                        media_type="application/pdf")


@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> Session:
    session = store.get(session_id)
    if not session:
        raise HTTPException(404, f"Session '{session_id}' not found.")
    return session


def _sse_with_id(event: dict) -> str:
    """Format an event as SSE with id: field for reconnection support."""
    event_id = event.get("id", "")
    data = json.dumps(event)
    return f"id: {event_id}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
