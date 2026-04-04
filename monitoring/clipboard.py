"""
monitoring/clipboard.py
Polls the clipboard every second.

Content classification:
  "text"  — regular text (stores first 350 chars as _snippet)
  "url"   — text that is entirely / mostly a URL
  "image" — Windows bitmap/DIB in clipboard (uses win32clipboard)

Snippets are in-memory only — never written to the database.
"""
import re
import threading
import time
from typing import Callable

import pyperclip

from utils.hashing import sha256_text
from utils.logger import get_logger

logger = get_logger(__name__)

POLL_INTERVAL = 1.0   # seconds

# Regex: matches http/https URLs or bare www. addresses
_URL_RE = re.compile(
    r'^(https?://|www\.)\S+',
    re.IGNORECASE,
)
_URL_INLINE = re.compile(r'https?://\S+', re.IGNORECASE)

# Try to import win32clipboard for image detection (pywin32)
try:
    import win32clipboard
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False
    logger.debug("win32clipboard not available — image detection disabled.")

# Windows clipboard format constants
CF_DIB      = 8      # Device-Independent Bitmap
CF_DIBV5    = 17


def _classify_text(text: str) -> tuple[str, str]:
    """
    Returns (content_type, snippet).
    content_type: 'url' | 'text'
    snippet: first 350 chars, stripped
    """
    stripped = text.strip()
    snippet  = stripped[:350]

    # Entire clipboard is a single URL
    if _URL_RE.match(stripped) and " " not in stripped.split("\n")[0]:
        return "url", stripped[:2000]   # store full URL for reporting

    # Text block containing embedded URLs
    found_urls = _URL_INLINE.findall(stripped)
    if found_urls:
        return "url_in_text", snippet

    return "text", snippet


def _check_clipboard_image() -> dict | None:
    """
    Returns image metadata dict if the Windows clipboard contains bitmap data,
    or None if no image is present.
    Never stores actual pixel data — only dimensions and format.
    """
    if not _HAS_WIN32:
        return None
    try:
        win32clipboard.OpenClipboard()
        try:
            has_dib   = win32clipboard.IsClipboardFormatAvailable(CF_DIB)
            has_dibv5 = win32clipboard.IsClipboardFormatAvailable(CF_DIBV5)
            if has_dib or has_dibv5:
                # Read the BITMAPINFOHEADER to get dimensions (first 40 bytes of DIB)
                fmt = CF_DIBV5 if has_dibv5 else CF_DIB
                data = win32clipboard.GetClipboardData(fmt)
                # BITMAPINFOHEADER: biWidth @ offset 4, biHeight @ offset 8 (both LONG, 4 bytes)
                if len(data) >= 12:
                    import struct
                    biWidth  = struct.unpack_from('<i', data, 4)[0]
                    biHeight = abs(struct.unpack_from('<i', data, 8)[0])
                    return {
                        "width" : biWidth,
                        "height": biHeight,
                        "size_bytes": len(data),
                    }
                return {"width": "?", "height": "?", "size_bytes": len(data)}
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        logger.debug("Image clipboard check failed: %s", exc)
    return None


class ClipboardMonitor:
    """
    Detects clipboard changes and fires `on_event(record: dict)`.

    Extended fields (all in-memory, never written to DB):
      _snippet       : first 350 chars of text (or "url" / image info string)
      _content_type  : "text" | "url" | "url_in_text" | "image"
      _approx_len    : character count of content
    """

    def __init__(self, on_event: Callable[[dict], None], session_id: str) -> None:
        self._on_event    = on_event
        self._session_id  = session_id
        self._last_hash   = ""     # hash of last TEXT clipboard content
        self._last_img_hash = ""   # fingerprint of last IMAGE seen (width×height×size)
        self._running     = False
        self._thread: threading.Thread | None = None
        self._event_count = 0

    def start(self) -> None:
        try:
            initial = pyperclip.paste() or ""
            self._last_hash = sha256_text(initial)
        except Exception:
            self._last_hash = ""

        img_info = _check_clipboard_image()
        if img_info:
            self._last_img_hash = f"{img_info['width']}x{img_info['height']}x{img_info['size_bytes']}"
        else:
            self._last_img_hash = ""

        self._running = True
        self._thread  = threading.Thread(
            target=self._poll, daemon=True, name="Clipboard-Monitor"
        )
        self._thread.start()
        logger.info("ClipboardMonitor started.")

    def stop(self) -> None:
        self._running = False
        logger.info("ClipboardMonitor stopped. Events: %d", self._event_count)

    @property
    def event_count(self) -> int:
        return self._event_count

    # ── poll ───────────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        while self._running:
            time.sleep(POLL_INTERVAL)

            # ── 1. Image check (Windows bitmap in clipboard) ──────────────────
            img_info = _check_clipboard_image()
            if img_info:
                # Build a stable fingerprint for THIS image
                img_fingerprint = f"{img_info['width']}x{img_info['height']}x{img_info['size_bytes']}"

                if img_fingerprint != self._last_img_hash:
                    # Genuinely new image — fire once
                    self._last_img_hash = img_fingerprint
                    # Reset text hash so pasting text after an image is detected
                    self._last_hash = ""
                    self._event_count += 1
                    snippet = (
                        f"[Image: {img_info['width']}×{img_info['height']} px, "
                        f"~{img_info['size_bytes'] // 1024} KB clipboard data]"
                    )
                    record = {
                        "session_id"   : self._session_id,
                        "timestamp"    : time.time(),
                        "event_type"   : "clipboard_change",
                        "chars_added"  : 0,
                        "clipboard"    : 1,
                        "typing_speed" : 0.0,
                        "suspicion"    : 1,
                        "payload_hash" : sha256_text(img_fingerprint),
                        "raw_json"     : None,
                        "_approx_len"  : img_info["size_bytes"],
                        "_snippet"     : snippet,
                        "_content_type": "image",
                    }
                    logger.debug("New image detected in clipboard: %s", snippet)
                    self._on_event(record)
                # else: same image still in clipboard — do nothing
                continue   # skip text poll this cycle

            # ── 2. Text check ─────────────────────────────────────────────────
            try:
                content = pyperclip.paste() or ""
            except Exception:
                continue

            current_hash = sha256_text(content)
            if current_hash == self._last_hash:
                continue

            self._last_hash   = current_hash
            self._event_count += 1
            approx_len        = len(content)

            if approx_len > 20:
                content_type, snippet = _classify_text(content)
            else:
                content_type, snippet = "text", content.strip()

            # Extract all URLs from the snippet for reporting
            found_urls = _URL_INLINE.findall(content[:2000])
            url_list   = found_urls[:10]   # cap at 10 URLs

            record = {
                "session_id"   : self._session_id,
                "timestamp"    : time.time(),
                "event_type"   : "clipboard_change",
                "chars_added"  : approx_len,
                "clipboard"    : 1,
                "typing_speed" : 0.0,
                "suspicion"    : 1 if approx_len > 150 else 0,
                "payload_hash" : current_hash,
                "raw_json"     : None,
                "_approx_len"  : approx_len,
                "_snippet"     : snippet,
                "_content_type": content_type,
                "_urls"        : url_list,   # list of embedded URLs (in-memory only)
            }
            logger.debug(
                "Clipboard changed — type=%s len=%d", content_type, approx_len
            )
            self._on_event(record)
