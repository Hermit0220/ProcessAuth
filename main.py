"""
main.py
ProcessAuth entry point.
1. Boots the Qt application with the glassmorphic stylesheet.
2. Shows the mandatory consent dialog.
3. On acceptance → launches the main dashboard.
4. Checks for incomplete sessions from previous crashes and offers recovery.
"""
import sys
import os
import time

# ── ensure project root is on sys.path ───────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtCore import Qt

from ui.consent import ConsentDialog
from ui.dashboard import Dashboard
from ui.styles import STYLESHEET
from database.db import db
from utils.logger import get_logger

logger = get_logger("main")


def check_crash_recovery(dashboard: Dashboard) -> None:
    """
    If any sessions exist in the DB with no end time, offer to generate
    a partial report from salvaged data.
    Sessions whose document no longer exists are silently dismissed.
    """
    try:
        db.start()
        incomplete = db.get_incomplete_sessions()

        # Auto-close sessions whose document file was deleted
        valid = []
        for s in incomplete:
            doc_path = s.get("doc_path") or ""
            if doc_path and not os.path.exists(doc_path):
                logger.info(
                    "Auto-dismissing stale session %s (doc deleted: %s)",
                    s.get("session_id", "")[:8], doc_path
                )
                db.close_session(s["session_id"], time.time(), 0.0)
            else:
                valid.append(s)

        db.stop()

        if not valid:
            return

        latest = valid[0]
        sid    = latest.get("session_id", "?")[:8]
        doc    = os.path.basename(latest.get("doc_path") or "Unknown")

        reply = QMessageBox.question(
            None,
            "Recover Previous Session?",
            f"A session was not closed properly.\n\n"
            f"Session: {sid}…\n"
            f"Document: {doc}\n\n"
            "Generate a partial authenticity report from the saved data?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            _recover_session(latest)

    except Exception as exc:
        logger.warning("Crash recovery check failed: %s", exc)


def _recover_session(session_data: dict) -> None:
    """Build a best-effort report from an incomplete session."""
    import time
    from analysis.behavioral_engine import BehavioralEngine, SessionStats
    from reports.generator import generate_report

    try:
        db.start()
        events = db.get_events(session_data["session_id"])
        db.stop()

        # Reconstruct stats from stored events
        engine = BehavioralEngine()
        for ev in events:
            engine.process_event(ev)

        stats = engine.get_stats()
        started_at = session_data.get("started_at") or time.time()
        ended_at   = time.time()

        path = generate_report(
            session_id=session_data["session_id"],
            doc_path=session_data.get("doc_path") or "recovered_session",
            stats=stats,
            suspicious_insertions=engine.suspicious_insertions,
            started_at=started_at,
            ended_at=ended_at,
            fmt="html",
        )

        QMessageBox.information(
            None, "Recovery Complete",
            f"Partial report generated:\n{path}"
        )

    except Exception as exc:
        logger.error("Session recovery failed: %s", exc)
        QMessageBox.warning(None, "Recovery Failed", str(exc))


def main() -> None:
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ProcessAuth")
    app.setApplicationVersion("1.0.0")
    app.setStyleSheet(STYLESHEET)

    # ── Consent ───────────────────────────────────────────────────────────────
    consent = ConsentDialog()
    consent.exec()

    if not consent.accepted_consent:
        logger.info("User declined consent. Exiting.")
        sys.exit(0)

    logger.info("Consent accepted. Launching dashboard.")

    # ── Crash recovery check ─────────────────────────────────────────────────
    check_crash_recovery(None)

    # ── Dashboard ─────────────────────────────────────────────────────────────
    win = Dashboard()
    win.show()
    win.raise_()
    win.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
