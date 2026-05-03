import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from monitoring.logger import get_logger
logger = get_logger(__name__)
DB_PATH = Path(__file__).parent / "sessions" / "agent_memory.db"
class AgentMemory:
    """
    Persistent memory for agents to recall previous experiences on specific URLs.
    """
    def __init__(self):
        self._init_db()
    def _init_db(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash TEXT,
                    persona_id TEXT,
                    experience_type TEXT, -- 'success', 'failure', 'observation'
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url_persona ON memory(url_hash, persona_id)")
    def _hash_url(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()
    def record_experience(self, url: str, persona_id: str, exp_type: str, content: str):
        """
        Save a new experience to the database.
        """
        url_hash = self._hash_url(url)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO memory (url_hash, persona_id, experience_type, content) VALUES (?, ?, ?, ?)",
                (url_hash, persona_id, exp_type, content)
            )
        logger.info("agent_memory.recorded", persona_id=persona_id, type=exp_type)
    def get_experiences(self, url: str, persona_id: str, limit: int = 5) -> List[Dict]:
        """
        Retrieve recent experiences for a persona on a specific URL.
        """
        url_hash = self._hash_url(url)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT experience_type, content, timestamp FROM memory WHERE url_hash = ? AND persona_id = ? ORDER BY timestamp DESC LIMIT ?",
                (url_hash, persona_id, limit)
            )
            rows = cursor.fetchall()
            return [
                {"type": r[0], "content": r[1], "ts": r[2]}
                for r in rows
            ]
    def format_memory_for_prompt(self, url: str, persona_id: str) -> str:
        """
        Returns a formatted string of memories for injection into agent prompts.
        """
        memories = self.get_experiences(url, persona_id)
        if not memories:
            return "No previous memories for this page."
        lines = ["### MEMORIES OF PREVIOUS RUNS ON THIS PAGE:"]
        for m in memories:
            lines.append(f"- [{m['type'].upper()} at {m['ts']}]: {m['content']}")
        return "\n".join(lines)
agent_memory = AgentMemory()