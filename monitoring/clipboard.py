"""
monitoring/clipboard.py
Polls the clipboard every second.
Stores only SHA-256 hashes of clipboard content — never raw text.
"""
import threading
import time
from typing import Callable

import pyperclip

from utils.hashing import sha256_text
from utils.logger import get_logger

logger = get_logger(__name__)

POLL_INTERVAL = 1.0   # seconds


class ClipboardMonitor:
    """
    Detects clipboard changes and fires `on_event(record: dict)`.
    Raw clipboard content is immediately hashed before any processing.
    """

    def __init__(self, on_event: Callable[[dict], None], session_id: str) -> None:
        self._on_event   = on_event
        self._session_id = session_id
        self._last_hash  = ""
        self._running    = False
        self._thread: threading.Thread | None = None
        self._event_count = 0

    def start(self) -> None:
        # Capture baseline so we don't fire on stale clipboard
        try:
            initial = pyperclip.paste() or ""
            self._last_hash = sha256_text(initial)
        except Exception:
            self._last_hash = ""

        self._running = True
        self._thread = threading.Thread(
            target=self._poll, daemon=True, name="Clipboard-Monitor"
        )
        self._thread.start()
        logger.info("ClipboardMonitor started.")

    def stop(self) -> None:
        self._running = False
        logger.info("ClipboardMonitor stopped. Total events: %d", self._event_count)

    @property
    def event_count(self) -> int:
        return self._event_count

    def _poll(self) -> None:
        while self._running:
            time.sleep(POLL_INTERVAL)
            try:
                content = pyperclip.paste() or ""
            except Exception:
                continue

            current_hash = sha256_text(content)
            if current_hash != self._last_hash:
                self._last_hash = current_hash
                self._event_count += 1
                approx_len = len(content)
                record = {
                    "session_id"  : self._session_id,
                    "timestamp"   : time.time(),
                    "event_type"  : "clipboard_change",
                    "chars_added" : approx_len,
                    "clipboard"   : 1,
                    "typing_speed": 0.0,
                    "suspicion"   : 1 if approx_len > 150 else 0,
                    "payload_hash": current_hash,
                    "raw_json"    : None,
                    "_approx_len" : approx_len,
                }
                logger.debug("Clipboard changed, len≈%d", approx_len)
                self._on_event(record)
