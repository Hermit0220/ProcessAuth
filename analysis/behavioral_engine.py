"""
analysis/behavioral_engine.py
Aggregates raw events from all monitors and applies tiered penalty scoring.

Authenticity Score formula:
    score = 100 - sum(penalties)
    clamped to [0, 100]

Penalty tiers:
  Tier 1 — burst < 60 chars     : 0
  Tier 2 — burst 60–200 chars   : -5
  Tier 3 — burst > 200 chars    : -15
  Clipboard correlation within 2 s of a large insert: additional -10
  Large paragraph block (> 150 chars, no keystroke lead-up): -10
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from utils.logger import get_logger

logger = get_logger(__name__)

CLIPBOARD_WINDOW   = 2.0   # seconds
TIER2_THRESHOLD    = 60
TIER3_THRESHOLD    = 200
PENALTY_TIER2      = 5
PENALTY_TIER3      = 15
PENALTY_CORRELATED = 10
PENALTY_BLOCK_INS  = 10


@dataclass
class SessionStats:
    total_keystrokes   : int   = 0
    total_chars_typed  : int   = 0
    total_chars_pasted : int   = 0
    backspaces         : int   = 0
    paste_events       : int   = 0
    suspicious_events  : int   = 0
    penalties          : float = 0.0
    authenticity_score : float = 100.0
    typing_speeds      : list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_keystrokes"  : self.total_keystrokes,
            "total_chars_typed" : self.total_chars_typed,
            "total_chars_pasted": self.total_chars_pasted,
            "backspaces"        : self.backspaces,
            "paste_events"      : self.paste_events,
            "suspicious_events" : self.suspicious_events,
            "penalties"         : round(self.penalties, 2),
            "authenticity_score": round(self.authenticity_score, 2),
            "avg_typing_speed"  : round(
                sum(self.typing_speeds) / len(self.typing_speeds)
                if self.typing_speeds else 0.0, 2
            ),
        }


class BehavioralEngine:
    """
    Consumes event records from all monitors and maintains running session stats.
    Thread-safe — all monitors push via `process_event()`.
    """

    def __init__(self, on_stats_update: Callable[[SessionStats], None] | None = None) -> None:
        self._stats   = SessionStats()
        self._lock    = threading.Lock()
        self._on_update = on_stats_update

        # Track clipboard timestamps for correlation
        self._clipboard_times: list[float] = []
        # Track doc diff events
        self._diff_events: list[dict] = []
        # Track suspicious insertion timestamps for report
        self.suspicious_insertions: list[dict] = []

    # ── public API ─────────────────────────────────────────────────────────────

    def process_event(self, record: dict) -> None:
        with self._lock:
            etype = record.get("event_type", "")
            ts    = record.get("timestamp", time.time())

            if etype == "key_press":
                self._handle_key(record)
            elif etype == "clipboard_change":
                self._handle_clipboard(record, ts)
            elif etype == "doc_diff":
                self._handle_diff(record, ts)

            self._recalc_score()

        if self._on_update:
            self._on_update(self._stats)

    def get_stats(self) -> SessionStats:
        with self._lock:
            return self._stats

    # ── handlers ──────────────────────────────────────────────────────────────

    def _handle_key(self, record: dict) -> None:
        self._stats.total_keystrokes  += 1
        self._stats.total_chars_typed += 1
        self._stats.backspaces        += record.get("_backspaces", 0)
        spd = record.get("typing_speed", 0.0)
        if spd > 0:
            self._stats.typing_speeds.append(spd)

    def _handle_clipboard(self, record: dict, ts: float) -> None:
        self._clipboard_times.append(ts)
        approx_len = record.get("_approx_len", record.get("chars_added", 0))
        if approx_len > TIER2_THRESHOLD:
            self._stats.paste_events += 1

    def _handle_diff(self, record: dict, ts: float) -> None:
        new_chars      = record.get("new_chars", 0)
        large_insert   = record.get("large_insertion", False)
        suspicious     = record.get("suspicious", False)

        self._stats.total_chars_pasted += new_chars if large_insert else 0

        penalty = 0.0
        reason  = []

        if new_chars > TIER3_THRESHOLD:
            penalty += PENALTY_TIER3
            reason.append(f"Tier-3 burst ({new_chars} chars)")
        elif new_chars > TIER2_THRESHOLD:
            penalty += PENALTY_TIER2
            reason.append(f"Tier-2 burst ({new_chars} chars)")

        # Clipboard correlation check
        correlated = any(
            abs(ts - ct) <= CLIPBOARD_WINDOW for ct in self._clipboard_times
        )
        if correlated and large_insert:
            penalty += PENALTY_CORRELATED
            reason.append("clipboard correlation")

        if large_insert and not correlated:
            penalty += PENALTY_BLOCK_INS
            reason.append("large block insertion, no clipboard signal")

        if penalty > 0:
            self._stats.suspicious_events += 1
            self._stats.penalties         += penalty
            self.suspicious_insertions.append({
                "timestamp"  : ts,
                "new_chars"  : new_chars,
                "penalty"    : penalty,
                "reasons"    : reason,
                "correlated" : correlated,
            })
            logger.info("Suspicious insertion: %s (penalty=%.0f)", reason, penalty)

    def _recalc_score(self) -> None:
        raw = 100.0 - self._stats.penalties
        self._stats.authenticity_score = max(0.0, min(100.0, raw))
