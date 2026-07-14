"""
SQLite-backed job store.

Replaces the previous in-memory dict, which lost all job state on every
backend restart. SQLite was chosen over Redis/Postgres: it's stdlib, needs no
extra service to run or deploy, and comfortably handles this app's single-
instance, single-user read/write volume.
"""

import json
import sqlite3
import threading
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    sections_complete INTEGER NOT NULL DEFAULT 0,
    total_sections INTEGER NOT NULL DEFAULT 0,
    events TEXT NOT NULL DEFAULT '[]',
    final_document TEXT,
    error TEXT
);
"""

_UPDATABLE_FIELDS = {
    "status", "artifact_type", "sections_complete", "total_sections",
    "events", "final_document", "error",
}


class JobStore:
    """Thread-safe (single-writer-lock) SQLite job store."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, job_id: str, artifact_type: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, status, artifact_type, events) VALUES (?, ?, ?, ?)",
                (job_id, "running", artifact_type, "[]"),
            )

    def update(self, job_id: str, **fields: Any) -> None:
        """Update only the given fields. Unknown keys are rejected to avoid
        accidental SQL injection via a stray field name."""
        unknown = set(fields) - _UPDATABLE_FIELDS
        if unknown:
            raise ValueError(f"Unknown job field(s): {unknown}")
        if not fields:
            return
        if "events" in fields:
            fields = {**fields, "events": json.dumps(fields["events"])}

        columns = ", ".join(f"{key} = ?" for key in fields)
        values = [*fields.values(), job_id]
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {columns} WHERE job_id = ?", values)

    def get(self, job_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["events"] = json.loads(job["events"])
        return job
