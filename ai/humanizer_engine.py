"""
ai/humanizer_engine.py
Orchestrator — routes user input to the right API pipeline.

Intent detection hierarchy:
  1. Forced mode (not "Auto") → use directly
  2. Auto → Gemini classifies intent → route to pipeline

Wikipedia / DuckDuckGo supply silent context — users never see raw API data.
"""
from __future__ import annotations

import re
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_WP_API  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_DDG_API = "https://api.duckduckgo.com/"
_TIMEOUT = 6


# ── Context helpers ────────────────────────────────────────────────────────────

def _wikipedia_summary(query: str) -> str:
    try:
        title = query.strip().replace(" ", "_")
        resp  = requests.get(
            _WP_API.format(title=title), timeout=_TIMEOUT,
            headers={"User-Agent": "ProcessAuth/1.0"}
        )
        if resp.status_code == 200:
            return resp.json().get("extract", "")
        return ""
    except Exception as exc:
        logger.debug("Wikipedia failed for '%s': %s", query, exc)
        return ""


def _duckduckgo_abstract(query: str) -> str:
    try:
        resp = requests.get(
            _DDG_API,
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=_TIMEOUT, headers={"User-Agent": "ProcessAuth/1.0"}
        )
        if resp.status_code == 200:
            data     = resp.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                return abstract
            return " ".join(
                item["Text"] for item in data.get("RelatedTopics", [])[:3]
                if isinstance(item, dict) and item.get("Text")
            )
        return ""
    except Exception as exc:
        logger.debug("DuckDuckGo failed for '%s': %s", query, exc)
        return ""


def _gather_context(query: str) -> str:
    ctx = _wikipedia_summary(query)
    if len(ctx) < 200:
        ctx += " " + _duckduckgo_abstract(query)
    return ctx[:3000].strip()


def _extract_topic(text: str) -> str:
    """Strip common question prefixes to get the core topic."""
    text = text.strip()
    for prefix in (
        "what is", "what are", "who is", "who was", "explain",
        "tell me about", "how does", "how do", "define", "what was",
        "describe", "give me info on", "info on", "about",
    ):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip(" ?.")
    return text


# ── Main entry point ───────────────────────────────────────────────────────────

def process(user_input: str, mode: str = "Auto", city: str = "") -> str:
    """
    Route user input to the correct pipeline.

    Parameters
    ----------
    user_input : str  The text or question from the user.
    mode       : str  "Auto" | "HumanRewrite" | "Ask" | "Facts" | "Summarize"
    city       : str  Used for weather queries in Facts mode.
    """
    from ai import gemini_client as gemini
    from ai import ninja_client  as ninja

    text = user_input.strip()
    if not text:
        return "Please type something first."

    # Auto-detect intent
    if mode == "Auto":
        mode = gemini.classify_intent(text)
        logger.info("Auto-detected mode: %s", mode)

    if mode == "HumanRewrite":
        return gemini.humanize(text)

    if mode == "Summarize":
        return gemini.summarize(text)

    if mode == "Ask":
        topic   = _extract_topic(text)
        context = _gather_context(topic) if len(topic) > 4 else ""
        return gemini.ask(text, context=context)

    if mode == "Facts":
        # Weather request?
        if re.search(
            r"\b(weather|temperature|temp|rain|humidity|forecast|hot|cold|degrees)\b",
            text, re.IGNORECASE
        ) and city.strip():
            return ninja.format_weather(ninja.get_weather(city.strip()))

        # Word definition?
        m = re.match(
            r"^\s*(define|meaning of|what does|what is)\s+\"?(\w+)\"?\s*\??$",
            text, re.IGNORECASE
        )
        if m:
            word = m.group(2)
            defs = ninja.get_word_definition(word)
            lines = [f"📖  {word.title()}"]
            for d in defs[:3]:
                pos = d.get("part_of_speech", "")
                dfn = d.get("definition", "")
                ex  = d.get("example", "")
                lines.append(f"\n({pos})  {dfn}" if pos else f"\n{dfn}")
                if ex:
                    lines.append(f'  e.g. "{ex}"')
            return "\n".join(lines)

        # General fact — enrich with Wikipedia/DDG
        topic   = _extract_topic(text)
        context = _gather_context(topic)
        return gemini.facts(text, context=context)

    # Fallback
    return gemini.ask(text)
