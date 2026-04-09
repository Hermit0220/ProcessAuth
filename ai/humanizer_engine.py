"""
ai/humanizer_engine.py
Orchestrator — routes to the correct pipeline.

Supports:
  - Local Ollama models (llama3.2, gemma3, processauth-* custom trained)
  - 🥷 Ninja (data-only: facts, weather, definitions via Ninja APIs + Wikipedia)
Wikipedia/DuckDuckGo context is gathered only when genuinely useful.
"""
from __future__ import annotations

import re
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_WP_API  = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_DDG_API = "https://api.duckduckgo.com/"
_TIMEOUT = 5


# ── Context helpers ────────────────────────────────────────────────────────────

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
    return text[:60]


# ── Main entry point ───────────────────────────────────────────────────────────

def process(user_input: str, mode: str = "Auto",
            llm_model: str = "", city: str = "") -> str:
    """
    Route user input to the correct pipeline based on mode and selected model.
    llm_model: the text currently shown in the Model dropdown.
    """
    from ai import ollama_client as ollama
    from ai import ninja_client  as ninja

    text = user_input.strip()
    if not text:
        return "Please type something first."

    # ── 🥷 Ninja engine: uses only Ninja APIs & Wikipedia — never Ollama ──────
    if llm_model and "ninja" in llm_model.lower():

        # HumanRewrite / Summarize → Ninja has no text-rewriting API
        if mode in ("HumanRewrite", "Summarize"):
            action = "rewrite" if mode == "HumanRewrite" else "summarize"
            return (
                f"🥷  Ninja doesn't support text {action}ing — it's a data engine.\n\n"
                f"To {action} this text, select a local model from the Model dropdown:\n"
                f"  •  ✦ Custom Trained · processauth-llama  (recommended)\n"
                f"  •  llama3.2:latest\n"
                f"  •  gemma3:1b\n\n"
                f"Make sure Ollama is running first (llama icon in your system tray)."
            )

        # Facts mode → Ninja APIs (weather, definitions) then Wikipedia
        if mode == "Facts":
            if re.search(
                r"\b(weather|temperature|temp|rain|humidity|forecast|hot|cold|degrees)\b",
                text, re.IGNORECASE
            ) and city.strip():
                return ninja.format_weather(ninja.get_weather(city.strip()))
            m_def = re.match(
                r"^\s*(define|meaning of|what does|what is)\s+\"?(\w+)\"?\s*\??$",
                text, re.IGNORECASE
            )
            if m_def:
                word = m_def.group(2)
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
            topic   = _extract_topic(text)
            context = _gather_context(topic)
            return f"\U0001f4da  {topic.title()}\n\n{context}" if context \
                   else f"🥷  No information found for '{topic}'. Try a more specific query."

        # Ask mode → Wikipedia + DuckDuckGo
        if mode == "Ask":
            topic   = _extract_topic(text)
            context = _gather_context(topic) if len(topic) > 4 else ""
            return f"\U0001f4ac  {topic.title()}\n\n{context}" if context \
                   else f"🥷  Couldn't find information on '{topic}' via Wikipedia/DuckDuckGo."

        # Auto → detect and route within Ninja
        local_mode = ollama.detect_mode_local(text)
        if local_mode == "HumanRewrite":
            return (
                "🥷  Auto detected: text rewrite requested.\n\n"
                "Ninja can't rewrite text — select a local Ollama model for this."
            )
        topic   = _extract_topic(text)
        context = _gather_context(topic)
        return f"\U0001f4ac  {topic.title()}\n\n{context}" if context \
               else f"🥷  No results found for '{topic}'."

    # ── AI Model Engine Selection ──────────────────────────────────────────────
    from ai import ollama_client as ollama
    from ai import gemini_client as gemini
    from ai import groq_client as groq
    
    model_lower = llm_model.lower()
    is_gemini = "gemini" in model_lower
    is_groq = "groq" in model_lower
    
    if is_gemini:
        target = gemini
    elif is_groq:
        target = groq
    else:
        target = ollama
        
    def _run(func_name: str, *args, **kwargs) -> str:
        """Call the target engine function, handling kwarg differences."""
        func = getattr(target, func_name, None)
        if not func:
            func = getattr(target, "humanize")
        if target == ollama:
            return func(*args, model=llm_model, **kwargs)
        return func(*args, **kwargs)

    # ── AI Processing ──────────────────────────────────────────────────────────
    if mode == "Auto":
        # Always use local heuristic to avoid wasting API calls on detection
        local_mode = ollama.detect_mode_local(text)
        if local_mode == "Facts":
            topic = _extract_topic(text)
            return _run("facts", text, context=_gather_context(topic))
        if local_mode == "Ask":
            topic = _extract_topic(text)
            return _run("ask", text, context=_gather_context(topic))
        if local_mode == "Summarize":
            return _run("summarize", text)
        return _run("humanize", text)

    if mode == "HumanRewrite":
        return _run("humanize", text)

    if mode == "Summarize":
        return _run("summarize", text)

    if mode == "Ask":
        topic   = _extract_topic(text)
        context = _gather_context(topic) if len(topic) > 4 else ""
        return _run("ask", text, context=context)

    if mode == "Facts":
        if re.search(
            r"\b(weather|temperature|temp|rain|humidity|forecast|hot|cold|degrees)\b",
            text, re.IGNORECASE
        ) and city.strip():
            return ninja.format_weather(ninja.get_weather(city.strip()))
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
        topic   = _extract_topic(text)
        context = _gather_context(topic)
        return _run("facts", text, context=context)

    # Fallback
    return _run("humanize", text)
