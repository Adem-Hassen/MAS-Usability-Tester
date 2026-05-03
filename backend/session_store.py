# backend/session_store.py
"""
In-memory session store with async SSE subscriber queues.
Supports event-ID-based reconnection via Last-Event-ID.
In production, replace with Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Optional
from fastapi import UploadFile

SESSIONS_DIR = Path(__file__).parent / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)


class SessionStatus(str, Enum):
    READY   = "ready"
    RUNNING = "running"
    DONE    = "done"
    FAILED  = "failed"


class EventKind(str, Enum):
    # New structured event types
    PIPELINE_START       = "pipeline_start"
    SUPERVISOR_ANALYSIS  = "supervisor_analysis"
    PERSONA_START        = "persona_start"
    PERSONA_ACTION       = "persona_action"
    PERSONA_COMPLETE     = "persona_complete"
    CLUSTERING_START     = "clustering_start"
    CLUSTERING_COMPLETE  = "clustering_complete"
    RECOMMENDER_START    = "recommender_start"
    RECOMMENDER_PATCH    = "recommender_patch"
    CONFLICT_DETECTED    = "conflict_detected"
    CONFLICT_RESOLVED    = "conflict_resolved"
    PATCH_APPLIED        = "patch_applied"
    PIPELINE_COMPLETE    = "pipeline_complete"
    ERROR                = "error"

    # Legacy event types (kept for backward compatibility)
    LOG      = "log"
    PROGRESS = "progress"
    STEP     = "step"
    ISSUE    = "issue"
    PATCH    = "patch"
    DONE     = "done"


# Terminal event types — SSE stream closes after emitting one of these
_TERMINAL_EVENTS = {
    EventKind.DONE, EventKind.ERROR,
    EventKind.PIPELINE_COMPLETE,
}


@dataclass
class Session:
    session_id:  str
    input_paths: list[Path]
    output_dir:  Path
    status:      SessionStatus = SessionStatus.READY
    progress:    int           = 0       # 0–100
    pages_done:  int           = 0
    created_at:  datetime      = field(default_factory=datetime.utcnow)
    started_at:  Optional[datetime] = None
    finished_at: Optional[datetime] = None
    results:     Optional[dict] = None
    error:       Optional[str]  = None


class SessionStore:
    def __init__(self):
        self._queues:   dict[str, list[asyncio.Queue]] = {}  # subscriber queues (ephemeral)
        self._active_tasks: dict[str, asyncio.Task] = {}     # currently running pipeline tasks
        self._loop: asyncio.AbstractEventLoop | None = None
        self._init_db()

    def _init_db(self):
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT,
                progress INTEGER,
                pages_done INTEGER,
                created_at TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                results TEXT,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                event_id INTEGER,
                kind TEXT,
                ts TEXT,
                payload TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Task tracking
    # ------------------------------------------------------------------

    def register_task(self, session_id: str, task: asyncio.Task):
        self._active_tasks[session_id] = task

    def unregister_task(self, session_id: str):
        self._active_tasks.pop(session_id, None)

    async def cancel_session(self, session_id: str):
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._active_tasks.pop(session_id, None)

    async def cancel_all(self):
        """Cancel all running pipelines."""
        tasks = list(self._active_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        
        if tasks:
            # Wait for them to finish/cancel
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._active_tasks.clear()
        
        # Force shutdown browser if any were running
        from agents.persona.playwright_engine import shutdown_shared_browser
        shutdown_shared_browser()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def create(self, session_id: str, files: list[UploadFile]) -> Session:
        self._loop = asyncio.get_running_loop()
        session_dir = SESSIONS_DIR / session_id
        input_dir   = session_dir / "input"
        output_dir  = session_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = []
        for f in files:
            dest = input_dir / f.filename
            content = await f.read()
            dest.write_bytes(content)
            paths.append(dest)
            await f.close() # Ensure file is closed after reading

        session = Session(
            session_id=session_id,
            input_paths=paths,
            output_dir=output_dir,
        )
        self._queues[session_id] = []
        
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, status, progress, pages_done, created_at) VALUES (?, ?, ?, ?, ?)",
                    (session_id, session.status.value, session.progress, session.pages_done, session.created_at.isoformat())
                )
        finally:
            conn.close()
        
        return session

    def _row_to_session(self, row: tuple) -> Session:
        """Helper to convert a DB row to a Session object."""
        # row: [session_id, status, progress, pages_done, created_at, started_at, finished_at, results, error]
        session_id = row[0]
        session_dir = SESSIONS_DIR / session_id
        input_dir = session_dir / "input"
        output_dir = session_dir / "output"
        paths = list(input_dir.glob("*.html"))
        
        results = None
        if row[7]:
            try:
                results = json.loads(row[7])
            except Exception:
                pass

        return Session(
            session_id=row[0],
            input_paths=paths,
            output_dir=output_dir,
            status=SessionStatus(row[1]),
            progress=row[2],
            pages_done=row[3],
            created_at=datetime.fromisoformat(row[4]),
            started_at=datetime.fromisoformat(row[5]) if row[5] else None,
            finished_at=datetime.fromisoformat(row[6]) if row[6] else None,
            results=results,
            error=row[8],
        )

    def get(self, session_id: str) -> Optional[Session]:
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        try:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return None
            return self._row_to_session(row)
        finally:
            conn.close()

    def delete(self, session_id: str) -> None:
        DB_PATH = SESSIONS_DIR / "sessions.db"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        
        self._queues.pop(session_id, None)
        session_dir = SESSIONS_DIR / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    def list_all(self) -> list[Session]:
        """Return all sessions from DB efficiently."""
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
            return [self._row_to_session(row) for row in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Event streaming
    # ------------------------------------------------------------------

    def emit(self, session_id: str, kind: str, **payload) -> None:
        """Emit an event to all subscribers and buffer it with an auto-incrementing ID."""
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        try:
            with conn:
                # Get next event_id for this session
                row = conn.execute(
                    "SELECT MAX(event_id) FROM events WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                event_id = (row[0] + 1) if (row and row[0] is not None) else 0

                ts = datetime.utcnow().isoformat()
                event = {
                    "id": event_id,
                    "kind": kind,
                    "ts": ts,
                    **payload,
                }

                conn.execute(
                    "INSERT INTO events (session_id, event_id, kind, ts, payload) VALUES (?, ?, ?, ?, ?)",
                    (session_id, event_id, kind, ts, json.dumps(payload))
                )
                
                # Special case: update session status if pipeline is done/failed
                if kind == EventKind.PIPELINE_COMPLETE:
                    conn.execute(
                        "UPDATE sessions SET status = ?, finished_at = ? WHERE session_id = ?",
                        (SessionStatus.DONE.value, ts, session_id)
                    )
                elif kind == EventKind.ERROR:
                    conn.execute(
                        "UPDATE sessions SET status = ?, finished_at = ?, error = ? WHERE session_id = ?",
                        (SessionStatus.FAILED.value, ts, payload.get("error", "Unknown error"), session_id)
                    )
                elif kind == EventKind.PIPELINE_START:
                    conn.execute(
                        "UPDATE sessions SET status = ?, started_at = ? WHERE session_id = ?",
                        (SessionStatus.RUNNING.value, ts, session_id)
                    )
        finally:
            conn.close()

        # Thread-safe: schedule put_nowait on the event loop from any thread
        loop = self._loop
        if loop is None:
            return
        for q in list(self._queues.get(session_id, [])):
            loop.call_soon_threadsafe(q.put_nowait, event)

    def get_events(self, session_id: str, after_id: int = -1) -> list[dict]:
        """Return buffered events from DB."""
        DB_PATH = SESSIONS_DIR / "sessions.db"
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = conn.execute(
                "SELECT event_id, kind, ts, payload FROM events WHERE session_id = ? AND event_id > ? ORDER BY event_id ASC",
                (session_id, after_id)
            ).fetchall()
            
            events = []
            for r in rows:
                try:
                    payload = json.loads(r[3])
                    events.append({
                        "id": r[0],
                        "kind": r[1],
                        "ts": r[2],
                        **payload
                    })
                except Exception:
                    continue
            return events
        finally:
            conn.close()

    def is_terminal(self, event: dict) -> bool:
        """Check if an event is terminal (should close the SSE stream)."""
        kind = event.get("kind", "")
        return kind in _TERMINAL_EVENTS

    async def subscribe(self, session_id: str) -> AsyncGenerator[dict, None]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(session_id, []).append(q)
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=120)
                yield event
                if self.is_terminal(event):
                    break
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                self._queues[session_id].remove(q)
            except (KeyError, ValueError):
                pass
