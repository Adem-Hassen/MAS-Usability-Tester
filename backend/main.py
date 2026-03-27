# backend/main.py
"""
Nexus Accessibility Evaluator — FastAPI Backend

Endpoints:
  POST /api/sessions          — create a session, upload up to 5 HTML files
  POST /api/sessions/{id}/run — trigger evaluation pipeline
  GET  /api/sessions/{id}/stream — SSE stream of live events
  GET  /api/sessions/{id}/results — final results JSON
  GET  /api/sessions/{id}/files/{filename} — download fixed HTML
  GET  /api/sessions/{id}/report.pdf — download PDF report
  GET  /api/sessions/{id}/status — quick status poll
"""

from __future__ import annotations
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks
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
    version="1.0.0",
    docs_url="/api/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SessionStore()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
async def stream_session(session_id: str):
    """Server-Sent Events stream of real-time pipeline events."""
    _get_session(session_id)  # validate exists

    async def event_generator() -> AsyncGenerator[str, None]:
        # Send buffered events first (for reconnect support)
        for ev in store.get_events(session_id):
           yield _sse(ev)

    # Heartbeat task — sends a comment every 15s to keep connection alive
        async def with_heartbeat():
          async for ev in store.subscribe(session_id):
             yield ev

        async for ev in with_heartbeat():
          yield _sse(ev)
          if ev.get("kind") in (EventKind.DONE, EventKind.ERROR):
            break
        # Yield a SSE comment as keepalive (browsers ignore comment lines)
          yield ": keepalive\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
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


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
