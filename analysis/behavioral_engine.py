"""
analysis/behavioral_engine.py
Aggregates raw events from all monitors and applies tiered penalty scoring.

Authenticity Score formula:
    score = 100 - sum(penalties)
    clamped to [0, 100]

Penalty tiers (clipboard-direct, fires immediately on paste — no file-save needed):
  Clipboard 150–300 chars      : -5
  Clipboard 300–600 chars      : -10
  Clipboard > 600 chars        : -18
  Clipboard burst reuse (< 3s) : additional -5
  External source confirmed    : additional -10

Doc-diff penalties (fires when Word doc is saved):
  Tier 2 burst 60–200 chars inserted : -5
  Tier 3 burst > 200 chars inserted  : -15
  Clipboard correlation within 2s    : additional -10
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Clipboard direct-penalty thresholds ──────────────────────────────────────
CLIP_SMALL         = 150    # chars — below this: no direct penalty
CLIP_MED           = 300    # chars
CLIP_LARGE         = 600    # chars
PENALTY_CLIP_MED   = 0
PENALTY_CLIP_LRG   = 0
PENALTY_CLIP_XLG   = 0
PENALTY_CLIP_BURST = 0     # if two large pastes within 3 s
PENALTY_URL_PASTE  = 0     # extra for pasting a bare URL — strong web signal
PENALTY_IMAGE_PASTE= 0     # pasting an image from clipboard
CLIP_BURST_WINDOW  = 3.0   # seconds

# ── Doc-diff thresholds ──────────────────────────────────────────────────────
CLIPBOARD_WINDOW   = 2.0
TIER2_THRESHOLD    = 60
TIER3_THRESHOLD    = 200
PENALTY_TIER2      = 0
PENALTY_TIER3      = 0
PENALTY_CORRELATED = 0
PENALTY_BLOCK_INS  = 0

# ── External source penalty ──────────────────────────────────────────────────
PENALTY_EXTERNAL   = 5


@dataclass
class SessionStats:
    total_keystrokes      : int   = 0
    total_chars_typed     : int   = 0
    total_chars_pasted    : int   = 0
    backspaces            : int   = 0
    paste_events          : int   = 0
    suspicious_events     : int   = 0
    external_hits         : int   = 0
    penalties             : float = 0.0
    authenticity_score    : float = 100.0
    typing_speeds         : list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_keystrokes"  : self.total_keystrokes,
            "total_chars_typed" : self.total_chars_typed,
            "total_chars_pasted": self.total_chars_pasted,
            "backspaces"        : self.backspaces,
            "paste_events"      : self.paste_events,
            "suspicious_events" : self.suspicious_events,
            "external_hits"     : self.external_hits,
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

    Score drops IMMEDIATELY on large clipboard events — no file-save required.
    """

    def __init__(self, on_stats_update: Callable[[SessionStats], None] | None = None) -> None:
        self._stats     = SessionStats()
        self._lock      = threading.Lock()
        self._on_update = on_stats_update

        # Clipboard timestamps for doc-diff correlation
        self._clipboard_times: list[float] = []
        # Track times of large clipboard events for burst detection
        self._clipboard_history: list[dict] = []
        # Suspicious insertions for final report
        self.suspicious_insertions: list[dict] = []
        # Penalties that are immune to refund (e.g. pasted images)
        self._non_refundable_penalties = 0.0

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
            elif etype == "external_hit":
                self._handle_external_hit(record, ts)

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
        # Only accumulate backspaces when we see a fresh count increase
        self._stats.backspaces = max(
            self._stats.backspaces,
            record.get("_backspaces", self._stats.backspaces)
        )
        spd = record.get("typing_speed", 0.0)
        if spd > 0:
            self._stats.typing_speeds.append(spd)

    def _handle_clipboard(self, record: dict, ts: float) -> None:
        """
        Records the clipboard event in history but DOES NOT penalize it yet.
        Penalties only apply if the clip makes its way into the document via `doc_diff`.
        """
        approx_len   = record.get("_approx_len", 0)
        snippet      = record.get("_snippet", "")
        content_type = record.get("_content_type", "text")
        urls         = record.get("_urls", [])

        # Maintain a rolling history of the last 20 clipboard items
        self._clipboard_history.append({
            "timestamp": ts,
            "approx_len": approx_len,
            "snippet": snippet,
            "content_type": content_type,
            "urls": urls
        })
        if len(self._clipboard_history) > 20:
            self._clipboard_history.pop(0)

    def _handle_diff(self, record: dict, ts: float) -> None:
        """
        Secondary penalty from doc-diff (fires when Word saves the file).
        Avoids double-counting chars already penalised by clipboard event.
        """
        new_chars    = record.get("new_chars", 0)
        deleted_chars= record.get("deleted_chars", 0)
        large_insert = record.get("large_insertion", False)
        
        # New parser properties
        new_images   = record.get("new_images", 0)
        new_urls     = record.get("new_urls", [])
        new_texts    = record.get("new_texts", [])

        penalty = 0.0
        reason  = []

        # ── Deletion Refund Logic ────────────────────────────────────────────────
        if deleted_chars > 0:
            refund = (deleted_chars / 50.0) * 1.5
            max_refundable = max(0.0, self._stats.penalties - self._non_refundable_penalties)
            actual_refund = min(refund, max_refundable)
            
            if actual_refund > 0:
                self._stats.penalties -= actual_refund
                logger.info("Refunded %.1f pts from %d deleted chars", actual_refund, deleted_chars)
                self.suspicious_insertions.append({
                    "timestamp"    : ts,
                    "new_chars"    : -deleted_chars,
                    "penalty"      : -round(actual_refund, 1),
                    "reasons"      : [f"Refund: deleted {deleted_chars} characters"],
                    "correlated"   : False,
                    "snippet"      : "",
                    "content_type" : "text",
                    "urls"         : [],
                })

        # ── Image Detection ──────────────────────────────────────────────────────
        if new_images > 0:
            # Check if there is an image in clipboard history to correlate with
            img_hist = [h for h in self._clipboard_history if h["content_type"] == "image"]
            snip = img_hist[-1]["snippet"] if img_hist else "Unknown source"
            self._stats.paste_events += new_images
            self._stats.suspicious_events += new_images
            self.suspicious_insertions.append({
                "timestamp"    : ts,
                "new_chars"    : 0,
                "penalty"      : PENALTY_IMAGE_PASTE,
                "reasons"      : [f"{new_images} image(s) inserted natively ({snip})"],
                "correlated"   : True,
                "snippet"      : snip,
                "content_type" : "image",
                "urls"         : [],
            })
            if img_hist:
                self._clipboard_history.remove(img_hist[-1])

        # ── URL Paste Detection ──────────────────────────────────────────────────
        if new_urls:
            url_hits = []
            for url in new_urls:
                # Correlate with clipboard
                match = next((h for h in self._clipboard_history if h["content_type"] in ("url","url_in_text") and url in h["urls"]), None)
                if match:
                    url_hits.append(url)
                    self._clipboard_history.remove(match)
            if url_hits:
                self._stats.paste_events += 1
                self._stats.suspicious_events += 1
                self.suspicious_insertions.append({
                    "timestamp"    : ts,
                    "new_chars"    : sum(len(u) for u in url_hits),
                    "penalty"      : PENALTY_URL_PASTE,
                    "reasons"      : [f"{len(url_hits)} URL(s) securely pasted into doc"],
                    "correlated"   : True,
                    "snippet"      : " ".join(url_hits),
                    "content_type" : "url",
                    "urls"         : url_hits,
                })

        # ── Text Match Detection ─────────────────────────────────────────────────
        correlated_chars = 0
        pasted_text_events = []
        logger.debug(f"DEBUG SYNC: Received {len(new_texts)} new_texts. Clipboard history size: {len(self._clipboard_history)}")
        for text in new_texts:
            t_clean = text.strip()
            logger.debug(f"DEBUG SYNC: Evaluating new text block length {len(t_clean)}: '{t_clean[:50]}...'")
            
            # Does this exactly match something in clipboard history?
            match = None
            for h in self._clipboard_history:
                if h["content_type"] == "text":
                    logger.debug(f"DEBUG SYNC: ... against clipboard snippet length {len(h['snippet'])}")
                    if t_clean in h["snippet"]:
                        match = h
                        break
            
            if match:
                logger.debug("DEBUG SYNC: Perfect Match Found!")
                self._clipboard_history.remove(match)
                cl = len(text)
                correlated_chars += cl
                if cl > CLIP_LARGE:
                    pasted_text_events.append(("very large clipboard native insertion", cl, PENALTY_CLIP_XLG))
                elif cl > CLIP_MED:
                    pasted_text_events.append(("large clipboard native insertion", cl, PENALTY_CLIP_LRG))
                elif cl > CLIP_SMALL:
                    pasted_text_events.append(("medium clipboard native insertion", cl, PENALTY_CLIP_MED))
                
                # Report it for UI
                if cl > CLIP_SMALL:
                    self._stats.paste_events += 1
                    self._stats.total_chars_pasted += cl
                    self._stats.suspicious_events += 1
                    self.suspicious_insertions.append({
                        "timestamp"    : ts,
                        "new_chars"    : cl,
                        "penalty"      : pasted_text_events[-1][2] if pasted_text_events else 0,
                        "reasons"      : [f"{pasted_text_events[-1][0]} ({cl} chars)"],
                        "correlated"   : True,
                        "snippet"      : text[:500],
                        "content_type" : "text",
                        "urls"         : [],
                    })

        # ── Uncorrelated Insert Logic (Typed very fast or unseen paste) ──────────
        new_chars = max(0, new_chars - correlated_chars)  # Ignore chars we proved were pasted
        if new_chars > TIER3_THRESHOLD:
            penalty += PENALTY_TIER3
            reason.append(f"Tier-3 doc insert ({new_chars} chars)")
        elif new_chars > TIER2_THRESHOLD:
            penalty += PENALTY_TIER2
            reason.append(f"Tier-2 doc insert ({new_chars} chars)")

        if large_insert and new_chars > 150: # Only if remaining chars > 150
            penalty += PENALTY_BLOCK_INS
            reason.append("large doc insert without clipboard signal")

        if penalty > 0:
            self._stats.suspicious_events += 1
            self._stats.penalties         += penalty
            self.suspicious_insertions.append({
                "timestamp"    : ts,
                "new_chars"    : new_chars,
                "penalty"      : penalty,
                "reasons"      : reason,
                "correlated"   : False,
                "snippet"      : "",
                "content_type" : "text",
                "urls"         : [],
            })
            logger.info("Doc-diff penalty: %s (-%.0f pts)", reason, penalty)

    def _handle_external_hit(self, record: dict, ts: float) -> None:
        """Called by ExternalChecker when a snippet matches web/Wikipedia content."""
        source  = record.get("source", "unknown")
        title   = record.get("match_title", "")
        snippet = record.get("_snippet", "")
        highlight = record.get("highlighted_html", snippet)
        
        self._stats.external_hits     += 1
        self._stats.suspicious_events += 1
        self._stats.penalties         += PENALTY_EXTERNAL
        self.suspicious_insertions.append({
            "timestamp"    : ts,
            "new_chars"    : record.get("chars_added", 0),
            "penalty"      : PENALTY_EXTERNAL,
            "reasons"      : [f"external source match ({source}): {title[:120]}"],
            "correlated"   : True,
            "snippet"      : highlight,
            "content_type" : "external",
            "urls"         : [],
            "source_url"   : title,
        })
        logger.info("External hit: %s — '%s' (-%d pts)", source, title[:60], PENALTY_EXTERNAL)

    def _recalc_score(self) -> None:
        raw = 100.0 - self._stats.penalties
        self._stats.authenticity_score = max(0.0, min(100.0, raw))
