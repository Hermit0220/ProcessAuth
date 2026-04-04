"""
core/session_manager.py
Orchestrates all monitoring threads and acts as the central event bus.
Handles graceful startup, pause/resume, and shutdown.
"""
import queue
import threading
import time
import uuid
from typing import Callable

from analysis.behavioral_engine import BehavioralEngine, SessionStats
from analysis.doc_parser import DocParser, DiffResult
from analysis.external_checker import ExternalChecker
from database.db import db
from monitoring.clipboard import ClipboardMonitor
from monitoring.file_watcher import FileWatcher
from monitoring.keyboard import KeyboardMonitor
from utils.logger import get_logger

logger = get_logger(__name__)


class SessionManager:
    """
    Central coordinator for a ProcessAuth monitoring session.
    All monitors push events into a shared queue; a dispatcher thread
    routes them to the BehavioralEngine and Database.
    """

    def __init__(
        self,
        doc_path: str,
        on_stats_update: Callable[[SessionStats], None] | None = None,
    ) -> None:
        self.session_id  = str(uuid.uuid4())
        self.doc_path    = doc_path
        self.started_at  = time.time()
        self._paused     = False
        self._running    = False

        self._event_queue: queue.Queue[dict | None] = queue.Queue()

        # Sub-systems
        self._engine   = BehavioralEngine(on_stats_update=on_stats_update)
        self._parser   = DocParser(doc_path, self._on_diff)
        self._kbd      = KeyboardMonitor(self._event_queue.put, self.session_id)
        self._clip     = ClipboardMonitor(self._event_queue.put, self.session_id)
        self._watcher  = FileWatcher(doc_path, self._parser.on_file_changed)
        # ExternalChecker — routes hits back through the event queue
        self._ext_checker = ExternalChecker(
            on_hit=self._event_queue.put,
            session_id=self.session_id,
            enabled=True,
        )

        self._dispatcher: threading.Thread | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        db.start()
        db.create_session(self.session_id, self.started_at, self.doc_path)

        self._parser.initial_snapshot()
        self._running = True

        self._dispatcher = threading.Thread(
            target=self._dispatch_loop, daemon=True, name="Dispatcher"
        )
        self._dispatcher.start()

        self._kbd.start()
        self._clip.start()
        self._watcher.start()
        self._ext_checker.start()

        logger.info("Session %s started for '%s'", self.session_id, self.doc_path)

    def pause(self) -> None:
        self._paused = True
        logger.info("Session paused.")

    def resume(self) -> None:
        self._paused = False
        logger.info("Session resumed.")

    def stop(self) -> float:
        """Stop all monitors and return the final authenticity score."""
        self._running = False
        self._event_queue.put(None)  # sentinel

        self._kbd.stop()
        self._clip.stop()
        self._watcher.stop()
        self._ext_checker.stop()

        if self._dispatcher:
            self._dispatcher.join(timeout=8)

        stats = self._engine.get_stats()
        score = stats.authenticity_score

        db.close_session(self.session_id, time.time(), score)
        db.stop()

        logger.info("Session %s ended. Score=%.1f", self.session_id, score)
        return score

    def get_stats(self) -> SessionStats:
        return self._engine.get_stats()

    def get_suspicious_insertions(self) -> list[dict]:
        return self._engine.suspicious_insertions

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_diff(self, diff: DiffResult) -> None:
        """Called by DocParser on every file change after debounce."""
        record = {
            "session_id"     : self.session_id,
            "timestamp"      : diff.timestamp,
            "event_type"     : "doc_diff",
            "chars_added"    : diff.new_chars,
            "clipboard"      : 0,
            "typing_speed"   : 0.0,
            "suspicion"      : 1 if diff.suspicious else 0,
            "payload_hash"   : None,
            "raw_json"       : None,
            # Extra fields for engine only
            "new_chars"      : diff.new_chars,
            "large_insertion": diff.large_insertion,
            "suspicious"     : diff.suspicious,
        }
        self._event_queue.put(record)
        
        # Submit naturally typed text blocks (paragraphs >= 80 chars) to plagiarism checker
        if getattr(diff, "new_texts", None):
            for snippet in diff.new_texts:
                self._ext_checker.submit(
                    snippet=snippet,
                    chars_len=len(snippet),
                    timestamp=diff.timestamp,
                )

    def _dispatch_loop(self) -> None:
        while self._running:
            try:
                record = self._event_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if record is None:
                break

            if self._paused:
                continue

            # For clipboard events — submit snippet to external checker (non-blocking)
            if record.get("event_type") == "clipboard_change":
                snippet = record.get("_snippet", "")
                if snippet:
                    self._ext_checker.submit(
                        snippet=snippet,
                        chars_len=record.get("_approx_len", 0),
                        timestamp=record.get("timestamp", time.time()),
                    )

            # Strip engine-only / in-memory-only keys before storing in DB
            db_record = {
                k: v for k, v in record.items()
                if not k.startswith("_") and k not in ("new_chars", "large_insertion")
            }
            db.log_event(db_record)
            self._engine.process_event(record)

        # Drain remaining on shutdown
        while not self._event_queue.empty():
            item = self._event_queue.get_nowait()
            if item:
                db_record = {
                    k: v for k, v in item.items()
                    if not k.startswith("_") and k not in ("new_chars", "large_insertion")
                }
                db.log_event(db_record)
