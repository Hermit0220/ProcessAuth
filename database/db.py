"""
database/db.py
SQLite-backed event store with:
  - Asynchronous batch-write queue (flush every 3 s or 50 events)
  - JSON fallback when DB is unavailable
  - Session recovery on startup
"""
import json
import os
import queue
import sqlite3
import threading
import time
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "processauth.db")
FALLBACK_PATH = os.path.join(DB_DIR, "Logs_Fallback.json")

FLUSH_INTERVAL = 3.0   # seconds
FLUSH_BATCH    = 50    # max records per flush


# ──────────────────────────────────────────────────────────────────────────────
# Schema helpers
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    timestamp    REAL    NOT NULL,
    event_type   TEXT    NOT NULL,
    chars_added  INTEGER DEFAULT 0,
    clipboard    INTEGER DEFAULT 0,
    typing_speed REAL    DEFAULT 0.0,
    suspicion    INTEGER DEFAULT 0,
    payload_hash TEXT,
    raw_json     TEXT
);
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   REAL NOT NULL,
    ended_at     REAL,
    doc_path     TEXT,
    final_score  REAL
);
"""


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(_CREATE_EVENTS)
    conn.execute(_CREATE_SESSIONS)
    conn.commit()
    return conn


# ──────────────────────────────────────────────────────────────────────────────
# Database Manager
# ──────────────────────────────────────────────────────────────────────────────

class DatabaseManager:
    """Thread-safe, batched SQLite writer with JSON fallback."""

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self._queue: queue.Queue[dict | None] = queue.Queue()
        self._fallback_buffer: list[dict] = []
        self._lock = threading.Lock()
        self._running = False
        self._worker: threading.Thread | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            self._conn = _open_db()
            logger.info("Database opened: %s", DB_PATH)
        except Exception as exc:
            logger.error("DB open failed, using JSON fallback: %s", exc)
            self._conn = None

        self._running = True
        self._worker = threading.Thread(target=self._flush_loop, daemon=True, name="DB-Writer")
        self._worker.start()

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)  # sentinel
        if self._worker:
            self._worker.join(timeout=8)
        self._write_fallback()
        if self._conn:
            self._conn.close()

    # ── public API ─────────────────────────────────────────────────────────────

    def log_event(self, record: dict) -> None:
        """Enqueue one event record (non-blocking)."""
        self._queue.put(record)

    def create_session(self, session_id: str, started_at: float, doc_path: str) -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, started_at, doc_path) VALUES(?,?,?)",
                (session_id, started_at, doc_path),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("create_session failed: %s", exc)

    def close_session(self, session_id: str, ended_at: float, final_score: float) -> None:
        if not self._conn:
            return
        try:
            self._conn.execute(
                "UPDATE sessions SET ended_at=?, final_score=? WHERE session_id=?",
                (ended_at, final_score, session_id),
            )
            self._conn.commit()
        except Exception as exc:
            logger.warning("close_session failed: %s", exc)

    def get_events(self, session_id: str) -> list[dict]:
        """Return all events for the given session as a list of dicts."""
        if not self._conn:
            return self._load_fallback_events(session_id)
        try:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY timestamp",
                (session_id,),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as exc:
            logger.error("get_events failed: %s", exc)
            return []

    def get_incomplete_sessions(self) -> list[dict]:
        """Sessions started but never closed — used for crash recovery."""
        if not self._conn:
            return []
        try:
            cur = self._conn.execute(
                "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC"
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as exc:
            logger.error("get_incomplete_sessions: %s", exc)
            return []

    # ── internal flush loop ────────────────────────────────────────────────────

    def _flush_loop(self) -> None:
        batch: list[dict] = []
        deadline = time.monotonic() + FLUSH_INTERVAL

        while self._running:
            try:
                timeout = max(0.1, deadline - time.monotonic())
                item = self._queue.get(timeout=timeout)
                if item is None:
                    break
                batch.append(item)
            except queue.Empty:
                pass

            if batch and (len(batch) >= FLUSH_BATCH or time.monotonic() >= deadline):
                self._flush(batch)
                batch = []
                deadline = time.monotonic() + FLUSH_INTERVAL

        # Drain remaining on shutdown
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item:
                batch.append(item)
        if batch:
            self._flush(batch)

    def _flush(self, batch: list[dict]) -> None:
        if self._conn:
            try:
                self._conn.executemany(
                    """INSERT INTO events
                       (session_id, timestamp, event_type, chars_added, clipboard,
                        typing_speed, suspicion, payload_hash, raw_json)
                       VALUES (:session_id,:timestamp,:event_type,:chars_added,:clipboard,
                               :typing_speed,:suspicion,:payload_hash,:raw_json)""",
                    batch,
                )
                self._conn.commit()
                return
            except Exception as exc:
                logger.error("DB flush failed, buffering to JSON: %s", exc)

        # Fallback: buffer in memory, write on stop
        self._fallback_buffer.extend(batch)

    def _write_fallback(self) -> None:
        if not self._fallback_buffer:
            return
        try:
            existing: list = []
            if os.path.exists(FALLBACK_PATH):
                with open(FALLBACK_PATH) as f:
                    existing = json.load(f)
            with open(FALLBACK_PATH, "w") as f:
                json.dump(existing + self._fallback_buffer, f, indent=2)
            logger.info("Fallback JSON written: %s", FALLBACK_PATH)
        except Exception as exc:
            logger.error("Fallback JSON write failed: %s", exc)

    def _load_fallback_events(self, session_id: str) -> list[dict]:
        if not os.path.exists(FALLBACK_PATH):
            return []
        try:
            with open(FALLBACK_PATH) as f:
                data = json.load(f)
            return [r for r in data if r.get("session_id") == session_id]
        except Exception:
            return []


# Module-level singleton
db = DatabaseManager()
