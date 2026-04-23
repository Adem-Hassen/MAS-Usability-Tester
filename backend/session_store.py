# backend/session_store.py
"""
In-memory session store with async SSE subscriber queues.
Supports event-ID-based reconnection via Last-Event-ID.
In production, replace with Redis pub/sub.
"""

from __future__ import annotations

import asyncio
import shutil
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
        self._sessions: dict[str, Session] = {}
        self._events:   dict[str, list[dict]] = {}       # buffered events (id-indexed)
        self._queues:   dict[str, list[asyncio.Queue]] = {}  # subscriber queues
        self._loop: asyncio.AbstractEventLoop | None = None
        self._event_counter: dict[str, int] = {}          # per-session event ID counter

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

        session = Session(
            session_id=session_id,
            input_paths=paths,
            output_dir=output_dir,
        )
        self._sessions[session_id] = session
        self._events[session_id]   = []
        self._queues[session_id]   = []
        self._event_counter[session_id] = 0
        return session

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._events.pop(session_id, None)
        self._queues.pop(session_id, None)
        self._event_counter.pop(session_id, None)
        session_dir = SESSIONS_DIR / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)

    # ------------------------------------------------------------------
    # Event streaming
    # ------------------------------------------------------------------

    def emit(self, session_id: str, kind: str, **payload) -> None:
        """Emit an event to all subscribers and buffer it with an auto-incrementing ID."""
        # Assign sequential event ID for Last-Event-ID reconnection
        event_id = self._event_counter.get(session_id, 0)
        self._event_counter[session_id] = event_id + 1

        event = {
            "id": event_id,
            "kind": kind,
            "ts": datetime.utcnow().isoformat(),
            **payload,
        }

        if session_id in self._events:
            self._events[session_id].append(event)

        # Thread-safe: schedule put_nowait on the event loop from any thread
        loop = self._loop
        if loop is None:
            return
        for q in list(self._queues.get(session_id, [])):
            loop.call_soon_threadsafe(q.put_nowait, event)

    def get_events(self, session_id: str, after_id: int = -1) -> list[dict]:
        """Return buffered events, optionally only those after a given event ID."""
        all_events = self._events.get(session_id, [])
        if after_id < 0:
            return list(all_events)
        return [e for e in all_events if e.get("id", 0) > after_id]

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
