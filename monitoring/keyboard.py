"""
monitoring/keyboard.py
Monitors keyboard activity using pynput.
Only records metrics (timing, key counts) — NO key content is stored.
Filters events to only process when a .docx document is the active window.
"""
import threading
import time
from collections import deque
from typing import Callable

from pynput import keyboard as kb

from utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_CHECK_INTERVAL = 2.0   # seconds between active-window polls


def _is_word_active() -> bool:
    """Return True if the foreground window belongs to Microsoft Word."""
    try:
        import ctypes
        import psutil

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc = psutil.Process(pid.value)
        return proc.name().upper() in ("WINWORD.EXE",)
    except Exception:
        return True   # fail open — keep monitoring


class KeyboardMonitor:
    """
    Tracks keystroke timing with privacy-safe metrics.
    Fires `on_event(record: dict)` for each meaningful measurement.
    """

    BURST_WINDOW   = 1.5   # seconds to consider a burst
    BURST_MIN_KEYS = 5     # minimum keys in BURST_WINDOW to trigger analysis

    def __init__(self, on_event: Callable[[dict], None], session_id: str) -> None:
        self._on_event   = on_event
        self._session_id = session_id
        self._listener: kb.Listener | None = None
        self._running    = False

        self._last_key_time: float | None = None
        self._recent_times: deque[float]  = deque(maxlen=200)
        self._total_keys   = 0
        self._backspaces   = 0
        self._lock         = threading.Lock()
        self._word_active  = False

        self._window_thread: threading.Thread | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._window_thread = threading.Thread(
            target=self._poll_window, daemon=True, name="Win-Watcher"
        )
        self._window_thread.start()
        self._listener = kb.Listener(
            on_press=self._on_press, suppress=False
        )
        self._listener.start()
        logger.info("KeyboardMonitor started.")

    def stop(self) -> None:
        self._running = False
        if self._listener:
            self._listener.stop()
        logger.info("KeyboardMonitor stopped.")

    # ── window polling ─────────────────────────────────────────────────────────

    def _poll_window(self) -> None:
        while self._running:
            self._word_active = _is_word_active()
            time.sleep(WINDOW_CHECK_INTERVAL)

    # ── key handler ───────────────────────────────────────────────────────────

    def _on_press(self, key: kb.Key | kb.KeyCode) -> None:
        if not self._word_active:
            return

        now = time.time()
        with self._lock:
            self._total_keys += 1
            if key == kb.Key.backspace:
                self._backspaces += 1

            gap = now - self._last_key_time if self._last_key_time else None
            self._last_key_time = now
            self._recent_times.append(now)

            record = self._build_record(now, gap)

        self._on_event(record)

    def _build_record(self, now: float, gap: float | None) -> dict:
        # Compute chars/min over the recent window
        cutoff = now - self.BURST_WINDOW
        burst_keys = sum(1 for t in self._recent_times if t >= cutoff)
        cpm = burst_keys / self.BURST_WINDOW * 60

        pause_detected = gap is not None and gap > 2.0

        return {
            "session_id"  : self._session_id,
            "timestamp"   : now,
            "event_type"  : "key_press",
            "chars_added" : 1,
            "clipboard"   : 0,
            "typing_speed": round(cpm, 2),
            "suspicion"   : 0,
            "payload_hash": None,
            "raw_json"    : None,
            # Extra fields used only by behavioral engine (not stored in DB as cols)
            "_gap"          : gap,
            "_pause"        : pause_detected,
            "_backspaces"   : self._backspaces,
            "_total_keys"   : self._total_keys,
        }
