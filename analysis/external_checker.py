"""
analysis/external_checker.py

Checks clipboard snippets against free, public web APIs to detect if pasted
content originates from an external online source.

APIs used (both are completely free — no API key required):
  1. DuckDuckGo Instant Answer API
     https://api.duckduckgo.com/?q={query}&format=json&no_html=1
  2. Wikipedia Search API
     https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json

Both are: no authentication, no signup, rate-limited by IP (~1 req/s is safe).
"""
import threading
import time
import urllib.parse
import urllib.request
import json
from typing import Callable

from utils.logger import get_logger

logger = get_logger(__name__)

# How many chars of the snippet to use as the search probe
PROBE_LEN       = 80
MIN_PROBE_LEN   = 30       # don't bother querying very short snippets
REQUEST_TIMEOUT = 6        # seconds
RATE_LIMIT      = 1.2      # seconds between requests (respect free APIs)


class ExternalChecker:
    """
    Receives clipboard snippets and queries DuckDuckGo + Wikipedia in a
    background thread. When a match is found, calls `on_hit(record: dict)`.

    on_hit record contains:
        event_type : "external_hit"
        source     : "duckduckgo" | "wikipedia"
        match_title: short string describing what matched
        chars_added: original clipboard snippet length
        timestamp  : float
        session_id : str
    """

    def __init__(
        self,
        on_hit: Callable[[dict], None],
        session_id: str,
        enabled: bool = True,
    ) -> None:
        self._on_hit      = on_hit
        self._session_id  = session_id
        self._enabled     = enabled
        self._queue: list[tuple[str, int, float]] = []   # (snippet, length, timestamp)
        self._lock        = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running     = False
        self._last_req    = 0.0

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._enabled:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="ExternalChecker"
        )
        self._thread.start()
        logger.info("ExternalChecker started (DuckDuckGo + Wikipedia).")

    def stop(self) -> None:
        self._running = False

    # ── public API ─────────────────────────────────────────────────────────────

    def submit(self, snippet: str, chars_len: int, timestamp: float) -> None:
        """Queue a snippet for external source checking (non-blocking)."""
        if not self._enabled or not snippet or len(snippet) < MIN_PROBE_LEN:
            return
        with self._lock:
            self._queue.append((snippet, chars_len, timestamp))

    # ── worker ─────────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while self._running:
            item = None
            with self._lock:
                if self._queue:
                    item = self._queue.pop(0)

            if item is None:
                time.sleep(0.5)
                continue

            snippet, chars_len, ts = item

            # Rate limit — be polite to free APIs
            elapsed = time.monotonic() - self._last_req
            if elapsed < RATE_LIMIT:
                time.sleep(RATE_LIMIT - elapsed)

            probe = self._build_probe(snippet)
            logger.debug("ExternalChecker probe: '%s…'", probe[:40])

            hit = self._query_duckduckgo(probe)
            if not hit:
                hit = self._query_wikipedia(probe)

            self._last_req = time.monotonic()

            if hit:
                record = {
                    "session_id"  : self._session_id,
                    "timestamp"   : ts,
                    "event_type"  : "external_hit",
                    "chars_added" : chars_len,
                    "source"      : hit["source"],
                    "match_title" : hit["title"],
                    "clipboard"   : 1,
                    "typing_speed": 0.0,
                    "suspicion"   : 1,
                    "payload_hash": None,
                    "raw_json"    : None,
                }
                logger.info(
                    "External source detected via %s: '%s'",
                    hit["source"], hit["title"][:60]
                )
                self._on_hit(record)

    # ── API queries ────────────────────────────────────────────────────────────

    def _build_probe(self, snippet: str) -> str:
        """Extract first meaningful sentence / phrase for querying."""
        text = snippet.strip()
        # Try to grab the first complete sentence
        for sep in (". ", "! ", "? ", "\n"):
            idx = text.find(sep)
            if MIN_PROBE_LEN <= idx <= PROBE_LEN:
                return text[: idx + 1].strip()
        return text[:PROBE_LEN].strip()

    def _query_duckduckgo(self, probe: str) -> dict | None:
        """
        DuckDuckGo Instant Answer API — free, no key.
        Returns a hit dict if the probe matches a known topic.
        """
        try:
            q   = urllib.parse.quote_plus(f'"{probe}"')
            url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(url, headers={"User-Agent": "ProcessAuth/1.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            abstract = data.get("Abstract", "").strip()
            title    = data.get("Heading", "").strip()

            if abstract and title:
                return {"source": "duckduckgo", "title": title}

            # RelatedTopics fallback
            topics = data.get("RelatedTopics", [])
            if topics and isinstance(topics[0], dict):
                text = topics[0].get("Text", "")
                if len(text) > 30:
                    return {"source": "duckduckgo", "title": text[:80]}

        except Exception as exc:
            logger.debug("DuckDuckGo query failed: %s", exc)

        return None

    def _query_wikipedia(self, probe: str) -> dict | None:
        """
        Wikipedia Search API — free, no key.
        Returns a hit dict if the probe matches a Wikipedia article.
        """
        try:
            q   = urllib.parse.quote_plus(probe)
            url = (
                f"https://en.wikipedia.org/w/api.php"
                f"?action=query&list=search&srsearch={q}&srlimit=1"
                f"&srnamespace=0&format=json&utf8="
            )
            req = urllib.request.Request(url, headers={"User-Agent": "ProcessAuth/1.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            results = data.get("query", {}).get("search", [])
            if results:
                title   = results[0].get("title", "")
                snippet = results[0].get("snippet", "")
                # Only flag if Wikipedia snippet closely overlaps with probe words
                probe_words = set(probe.lower().split())
                snip_words  = set(snippet.lower().split())
                overlap = len(probe_words & snip_words) / max(len(probe_words), 1)
                if overlap > 0.45:   # >45% word overlap → likely match
                    return {"source": "wikipedia", "title": title}

        except Exception as exc:
            logger.debug("Wikipedia query failed: %s", exc)

        return None
