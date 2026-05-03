import sqlite3
import json
from pathlib import Path

DB_PATH = Path("backend/sessions/sessions.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- Sessions ---")
cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)

print("\n--- Events ---")
cursor.execute("SELECT * FROM events ORDER BY id DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)

conn.close()
