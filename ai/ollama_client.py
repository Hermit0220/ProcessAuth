"""
ai/ollama_client.py
Wrapper around the local Ollama daemon (http://127.0.0.1:11434).
Drop-in replacement for groq_client in humanizer_engine.py.
"""
from __future__ import annotations

import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE         = "http://127.0.0.1:11434"
_TIMEOUT      = 120
_DEFAULT      = "llama3.2:latest"


# ── Core request ──────────────────────────────────────────────────────────────

def _call(prompt: str, system: str = "", model: str | None = None) -> str:
    mdl = (model or "").strip()
    if "\u00b7" in mdl:
        mdl = mdl.split("\u00b7")[-1].strip()
    if not mdl:
        mdl = _DEFAULT

    payload = {"model": mdl, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system

    try:
        resp = requests.post(f"{_BASE}/api/generate", json=payload, timeout=_TIMEOUT)
        if resp.status_code == 404:
            logger.error("Ollama API Error 404: %s", resp.text)
            return (
                f"Ollama Error: The model '{mdl}' was not found.\n"
                f"Please run 'ollama pull {mdl}' in your terminal."
            )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return (
            "\u26a0  Cannot connect to local Ollama.\n"
            "Make sure Ollama is installed and running "
            "(look for the llama icon in your system tray)."
        )
    except Exception as exc:
        logger.error("Ollama _call error: %s", exc)
        return f"\u26a0  Local AI error: {exc}"


# ── Model discovery ───────────────────────────────────────────────────────────

def fetch_local_models() -> list[str]:
    try:
        resp = requests.get(f"{_BASE}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return []


# ── Local intent classifier ───────────────────────────────────────────────────

def detect_mode_local(text: str) -> str:
    t = text.lower().strip()
    if any(k in t for k in ("rewrite", "humanize", "improve", "rephrase",
                             "make this sound", "fix my", "paraphrase", "more human")):
        return "HumanRewrite"
    if any(k in t for k in ("summarize", "summary", "condense", "tldr",
                             "key points", "brief", "shorten")):
        return "Summarize"
    if any(k in t for k in ("weather", "temperature", "define ", "definition of",
                             "what does", "meaning of", "how many", "population")):
        return "Facts"
    if any(k in t for k in ("what is", "what are", "who is", "who was", "how does",
                             "why is", "explain", "tell me about", "describe")) or t.endswith("?"):
        return "Ask"
    if len(text) > 200 and "?" not in text:
        return "HumanRewrite"
    return "Ask"


# ── Public LLM methods ────────────────────────────────────────────────────────

def smart_respond(text: str, context: str = "", model: str = None) -> str:
    sys = (
        "You are an expert AI behavioral humanizer. Process the user input exactly as instructed. "
        "Remove all AI-like patterns. Output ONLY the final content. Never apologize or refuse."
    )
    prompt = f"[CONTEXT]\n{context}\n\n[INPUT]\n{text}" if context else f"[INPUT]\n{text}"
    return _call(prompt, system=sys, model=model)


def humanize(text: str, model: str = None) -> str:
    sys = (
        "You are an expert human copywriter. Rewrite the text to bypass AI detection software.\n"
        "Rules:\n"
        "1. Mix short and long sentences aggressively.\n"
        "2. Use unexpected word choices — avoid the most obvious synonym.\n"
        "3. Never use: 'In conclusion', 'Furthermore', 'Moreover', 'It is important to note'.\n"
        "4. Add natural anchors: 'Honestly,', 'Well,', 'To be fair,', 'Here's the thing'\n"
        "5. Vary paragraph lengths. One-line paragraphs are powerful.\n"
        "Output ONLY the rewritten text. No intro, no explanation."
    )
    return _call(text, system=sys, model=model)


def summarize(text: str, model: str = None) -> str:
    sys = (
        "Summarize the text concisely. Extract key ideas in plain, natural language. "
        "No bullet points unless asked. 2-4 short paragraphs max. Output ONLY the summary."
    )
    return _call(text, system=sys, model=model)


def ask(prompt: str, context: str = "", model: str = None) -> str:
    sys = "Answer clearly and naturally — like a knowledgeable friend, not a textbook. Be concise but complete."
    if context.strip():
        sys += f"\nReference:\n---\n{context[:2500]}\n---"
    return _call(prompt, system=sys, model=model)


def facts(topic: str, context: str = "", model: str = None) -> str:
    sys = "Provide accurate, interesting information. Write naturally — no lists unless asked. Under 200 words."
    if context.strip():
        sys += f"\nBackground:\n---\n{context[:2500]}\n---"
    return _call(topic, system=sys, model=model)


def academic(text: str, model: str = None) -> str:
    sys = "Rewrite in formal academic prose. Use sophisticated vocabulary but avoid AI clichés."
    return _call(text, system=sys, model=model)


def creative(text: str, model: str = None) -> str:
    sys = "Rewrite to sound creative, vibrant, and engaging. Avoid rigid structures."
    return _call(text, system=sys, model=model)


def simplify(text: str, model: str = None) -> str:
    sys = "Rewrite so an 8th grader can understand it effortlessly."
    return _call(text, system=sys, model=model)


def grammar(text: str, model: str = None) -> str:
    sys = "Fix grammar, spelling, and flow. Change as little as possible."
    return _call(text, system=sys, model=model)
