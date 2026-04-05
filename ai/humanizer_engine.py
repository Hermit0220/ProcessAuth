"""
ai/humanizer_engine.py
Orchestrator — routes to the correct pipeline.

Auto mode now uses a SINGLE Gemini call via smart_respond().
Manual modes use their specific 1-call functions.
Wikipedia/DuckDuckGo context is gathered only when genuinely useful.
"""
from __future__ import annotations

import re
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_WP_API  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_DDG_API = "https://api.duckduckgo.com/"
_TIMEOUT = 5  # short timeout so slow context doesn't delay responses


def _wikipedia_summary(query: str) -> str:
    try:
        title = query.strip().replace(" ", "_")
        resp  = requests.get(
            _WP_API.format(title=title), timeout=_TIMEOUT,
            headers={"User-Agent": "ProcessAuth/1.0"}
        )
        if resp.status_code == 200:
            return resp.json().get("extract", "")[:2000]
        return ""
    except Exception:
        return ""


def _duckduckgo_abstract(query: str) -> str:
    try:
        resp = requests.get(
            _DDG_API,
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=_TIMEOUT, headers={"User-Agent": "ProcessAuth/1.0"}
        )
        if resp.status_code == 200:
            data = resp.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                return abstract
            return " ".join(
                item["Text"] for item in data.get("RelatedTopics", [])[:2]
                if isinstance(item, dict) and item.get("Text")
            )
        return ""
    except Exception:
        return ""


def _gather_context(query: str) -> str:
    ctx = _wikipedia_summary(query)
    if len(ctx) < 150:
        ctx += " " + _duckduckgo_abstract(query)
    return ctx[:2500].strip()


def _extract_topic(text: str) -> str:
    text = text.strip()
    for prefix in (
        "what is", "what are", "who is", "who was", "explain",
        "tell me about", "how does", "how do", "define", "what was",
        "describe", "about",
    ):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip(" ?.")
    return text[:60]   # cap to avoid huge Wikipedia queries


# ── Context is only fetched for Ask and Facts modes on non-trivial topics ──────

def _needs_context(mode: str, text: str) -> bool:
    """Only fetch external context for knowledge-heavy modes, not rewrites."""
    if mode in ("HumanRewrite", "Summarize"):
        return False
    topic_len = len(_extract_topic(text))
    return topic_len > 4


# ── Main entry point ───────────────────────────────────────────────────────────

def process(user_input: str, mode: str = "Auto", city: str = "") -> str:
    """
    Route user input to the correct pipeline.
    Auto mode = 1 Gemini call.
    Manual modes = 1 Gemini call each.
    """
    from ai import groq_client as gemini
    from ai import ninja_client  as ninja

    text = user_input.strip()
    if not text:
        return "Please type something first."

    # ── Auto: single smart call (no pre-classification) ───────────────────────
    if mode == "Auto":
        # Gather context quickly for knowledge topics
        local_mode = gemini.detect_mode_local(text)
        context = ""
        if local_mode in ("Ask", "Facts"):
            topic   = _extract_topic(text)
            context = _gather_context(topic)
        return gemini.smart_respond(text, context=context)

    # ── HumanRewrite ──────────────────────────────────────────────────────────
    if mode == "HumanRewrite":
        return gemini.humanize(text)

    # ── Summarize ─────────────────────────────────────────────────────────────
    if mode == "Summarize":
        return gemini.summarize(text)

    # ── Ask ───────────────────────────────────────────────────────────────────
    if mode == "Ask":
        topic   = _extract_topic(text)
        context = _gather_context(topic) if len(topic) > 4 else ""
        return gemini.ask(text, context=context)

    # ── Facts ─────────────────────────────────────────────────────────────────
    if mode == "Facts":
        # Weather?
        if re.search(
            r"\b(weather|temperature|temp|rain|humidity|forecast|hot|cold|degrees)\b",
            text, re.IGNORECASE
        ) and city.strip():
            return ninja.format_weather(ninja.get_weather(city.strip()))

        # Definition?
        m = re.match(
            r"^\s*(define|meaning of|what does|what is)\s+\"?(\w+)\"?\s*\??$",
            text, re.IGNORECASE
        )
        if m:
            word = m.group(2)
            defs = ninja.get_word_definition(word)
            lines = [f"\U0001f4d6  {word.title()}"]
            for d in defs[:3]:
                pos = d.get("part_of_speech", "")
                dfn = d.get("definition", "")
                ex  = d.get("example", "")
                lines.append(f"\n({pos})  {dfn}" if pos else f"\n{dfn}")
                if ex:
                    lines.append(f'  e.g. "{ex}"')
            return "\n".join(lines)

        # General fact with context
        topic   = _extract_topic(text)
        context = _gather_context(topic)
        return gemini.facts(text, context=context)

    # Fallback
    return gemini.smart_respond(text)
