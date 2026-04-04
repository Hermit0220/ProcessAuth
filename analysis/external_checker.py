"""
analysis/external_checker.py

Checks clipboard snippets against free, public web APIs to detect if pasted
content originates from an external online source.

APIs/Sources used (all free):
  1. DuckDuckGo HTML web search (`html.duckduckgo.com`)
     Used to find exact quote matches across the *entire* web.
  2. Wikipedia Search API
     Fallback exact match on Wikipedia articles.

Both are rate-limited by IP (~1 req/s is safe).
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

            hit = self._query_duckduckgo(probe, snippet)
            if not hit:
                hit = self._query_wikipedia(probe, snippet)

            self._last_req = time.monotonic()

            if hit:
                record = {
                    "session_id"  : self._session_id,
                    "timestamp"   : ts,
                    "event_type"  : "external_hit",
                    "chars_added" : chars_len,
                    "source"      : hit["source"],
                    "match_title" : hit["title"],
                    "_snippet"    : snippet,       # in-memory only
                    "highlighted_html": hit.get("highlighted_html", snippet),
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

    def _query_duckduckgo(self, probe: str, snippet: str) -> dict | None:
        """
        DuckDuckGo HTML query — finds exact quote matches across the web.
        """
        try:
            # We search for the exact quote to see if it's ripped from a site
            q   = urllib.parse.quote_plus(f'"{probe}"')
            url = "https://html.duckduckgo.com/html/"
            data = urllib.parse.urlencode({"q": q}).encode("utf-8")
            # DuckDuckGo requires a real-looking User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
            }
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Basic scrape — if there is a result snippet, it means a match was found.
            # We extract the title roughly using string ops to avoid external HTML parser dependency.
            if "result__snippet" in html:
                title = "Web Match Found"
                try:
                    start_title = html.find('class="result__title"')
                    if start_title != -1:
                        a_start = html.find('<a class="result__url"', start_title)
                        if a_start != -1:
                            href_end = html.find('>', a_start)
                            end_tag = html.find('</a>', href_end)
                            raw_url = html[href_end+1:end_tag].strip()
                            if raw_url:
                                title = raw_url.replace(" ", "").replace("\n", "")
                except Exception:
                    pass
                
                # Fetch contents of the matched URL and generate highlight
                highlighted_html = self._fetch_and_highlight(title, snippet)
                
                return {"source": "duckduckgo", "title": title, "highlighted_html": highlighted_html}

        except Exception as exc:
            logger.debug("DuckDuckGo HTML query failed: %s", exc)

        return None

    def _fetch_and_highlight(self, url: str, snippet: str) -> str:
        """Download remote webpage and highlight exact word matches against the copied snippet."""
        if not url.startswith("http"):
            url = f"https://{url}"
        
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                
            import re
            body = re.search(r'<body[^>]*>(.*?)</body>', html, re.IGNORECASE | re.DOTALL)
            text = body.group(1) if body else html
            
            text = re.sub(r'<script.*?>.*?</script>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<style.*?>.*?</style>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            web_text = re.sub(r'\s+', ' ', text).strip()
            
            return self._highlight_matches(snippet, web_text)
        except Exception as exc:
            logger.debug("Failed to fetch/highlight URL %s: %s", url, exc)
            return self._highlight_matches(snippet, snippet) # fallback: highlight entirely

    def _highlight_matches(self, pasted_text: str, web_text: str) -> str:
        import difflib
        import re
        pasted_tokens = [t for t in re.split(r'(\s+)', pasted_text) if t]
        web_tokens = [t for t in re.split(r'(\s+)', web_text) if t]
        
        sm = difflib.SequenceMatcher(None, [t.lower() for t in pasted_tokens], [t.lower() for t in web_tokens])
        out = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            chunk = ''.join(pasted_tokens[i1:i2])
            if not chunk: continue
            if tag == 'equal':
                if chunk.strip():
                    out.append(f'<mark style="background-color: #f472b6; color: #111827; padding: 0 1px; border-radius: 2px;">{chunk}</mark>')
                else:
                    out.append(chunk)
            else:
                out.append(chunk)
        return ''.join(out)

    def _query_wikipedia(self, probe: str, snippet: str) -> dict | None:
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
                    wiki_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    highlighted_html = self._fetch_and_highlight(wiki_url, snippet)
                    return {"source": "wikipedia", "title": wiki_url, "highlighted_html": highlighted_html}

        except Exception as exc:
            logger.debug("Wikipedia query failed: %s", exc)

        return None
