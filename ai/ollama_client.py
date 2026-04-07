"""
ai/ollama_client.py
Wrapper around the local Ollama daemon (http://127.0.0.1:11434).
Implements the same method signatures as groq_client so it is a
drop-in replacement in humanizer_engine.py.
"""
from __future__ import annotations

import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE    = "http://127.0.0.1:11434"
_TIMEOUT = 120   # local models can be slow on first run
_DEFAULT = "llama3.2:latest"


# ── Core request ──────────────────────────────────────────────────────────────

def _call(prompt: str, system: str = "", model: str | None = None) -> str:
    """Send a single generate request to the local Ollama daemon."""
    mdl = (model or "").strip()
    # Strip display-name prefix we added in the UI (e.g. "✦ Custom Trained · processauth-llama")
    if "·" in mdl:
        mdl = mdl.split("·")[-1].strip()
    if not mdl:
        mdl = _DEFAULT

    payload = {
        "model": mdl,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        resp = requests.post(
            f"{_BASE}/api/generate",
            json=payload,
            timeout=_TIMEOUT,
        )
        if resp.status_code == 404:
            name = mdl
            logger.error("Ollama API Error 404: %s", resp.text)
            return (
                f"Ollama Error: The model '{name}' was not found.\n"
                f"Please run 'ollama pull {name}' in your terminal."
            )
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "").strip()

    except requests.exceptions.ConnectionError:
        return (
            "⚠  Cannot connect to local Ollama.\n"
            "Make sure Ollama is installed and running "
            "(look for the llama icon in your system tray)."
        )
    except Exception as exc:
        logger.error("Ollama _call error: %s", exc)
        return f"⚠  Local AI error: {exc}"


# ── Model discovery ───────────────────────────────────────────────────────────

def fetch_local_models() -> list[str]:
    """Return a list of installed Ollama model names, e.g. ['llama3.2:latest', ...]."""
    try:
        resp = requests.get(f"{_BASE}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        return [m["name"] for m in models]
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return []


# ── Local intent classifier (no API cost) ────────────────────────────────────

def detect_mode_local(text: str) -> str:
    t = text.lower().strip()
    rewrite_kw = ("rewrite", "humanize", "improve", "rephrase", "make this sound",
                  "make it sound", "fix my", "paraphrase", "natural", "more human")
    summarize_kw = ("summarize", "summary", "condense", "tldr", "tl;dr",
                    "key points", "brief", "shorten", "main points")
    facts_kw = ("weather", "temperature", "define ", "definition of",
                "what does", "meaning of", "fact about", "news about",
                "how many", "how much", "population", "capital of")
    ask_kw = ("what is", "what are", "who is", "who was", "how does", "how do",
              "why is", "why does", "explain", "tell me about", "describe")

    if any(k in t for k in rewrite_kw):
        return "HumanRewrite"
    if any(k in t for k in summarize_kw):
        return "Summarize"
    if any(k in t for k in facts_kw):
        return "Facts"
    if any(k in t for k in ask_kw) or t.endswith("?"):
        return "Ask"
    if len(text) > 200 and "?" not in text:
        return "HumanRewrite"
    return "Ask"


# ── Public LLM methods ────────────────────────────────────────────────────────

def smart_respond(text: str, context: str = "", model: str = None) -> str:
    sys_prompt = (
        "You are an expert AI behavioral humanizer. Your task is to process the user's "
        "input exactly according to their explicit or implicit instructions. "
        "Remove all AI-like patterns (robotic structure, rigid lists, overly formal tone, repetitive structures). "
        "Output ONLY the final requested content. Never apologize, never refuse, never include your thought process."
    )
    if context:
        prompt = f"[BACKGROUND CONTEXT (Optional)]\n{context}\n\n[USER INPUT TO PROCESS]\n{text}"
    else:
        prompt = f"[USER INPUT TO PROCESS]\n{text}"

    return _call(prompt, system=sys_prompt, model=model)


def humanize(text: str, model: str = None) -> str:
    sys = (
        "You are an expert human copywriter and ghostwriter. Your absolute priority is to "
        "rewrite the provided text so that it completely bypasses AI detection software. "
        "Rules:\n"
        "1. Write with high 'burstiness' (mix extremely short, punchy sentences with longer, complex ones).\n"
        "2. Keep 'perplexity' high (use slightly unexpected word choices or unique phrasing instead of predictable vocabulary).\n"
        "3. Never use classic AI tells: avoid 'In conclusion', 'It is important to note', 'Furthermore', or 'Moreover'.\n"
        "4. Include slight, natural imperfections. Use conversational transitions like 'Honestly,', 'Well,', or 'To be fair,'.\n"
        "5. Output ONLY the rewritten text, nothing else. No introductions or apologies."
    )
    return _call(text, system=sys, model=model)


def summarize(text: str, model: str = None) -> str:
    sys = (
        "Summarize the following text concisely. Extract the key ideas in plain, natural language. "
        "Do NOT use bullet points unless the user asks. Write 2-4 short paragraphs maximum. "
        "Output ONLY the summary."
    )
    return _call(text, system=sys, model=model)


def ask(prompt: str, context: str = "", model: str = None) -> str:
    sys = "Answer the following clearly and naturally — like a knowledgeable friend, not a textbook. Be concise but complete."
    if context.strip():
        sys += f"\nReference:\n---\n{context[:2500]}\n---\n"
    return _call(prompt, system=sys, model=model)


def facts(topic: str, context: str = "", model: str = None) -> str:
    sys = "Provide accurate, interesting information on the following topic. Write naturally — no lists unless asked. Under 200 words unless more is needed."
    if context.strip():
        sys += f"\nBackground:\n---\n{context[:2500]}\n---\n"
    return _call(topic, system=sys, model=model)


def academic(text: str, model: str = None) -> str:
    sys = "Rewrite the following text in formal academic prose. Use sophisticated vocabulary but avoid AI-clichés."
    return _call(text, system=sys, model=model)


def creative(text: str, model: str = None) -> str:
    sys = "Rewrite the following text to sound creative, vibrant, and engaging. Avoid rigid structures."
    return _call(text, system=sys, model=model)


def simplify(text: str, model: str = None) -> str:
    sys = "Explain or rewrite the following text simply, so an 8th grader can understand it effortlessly."
    return _call(text, system=sys, model=model)


def grammar(text: str, model: str = None) -> str:
    sys = "Fix the grammar, spelling, and flow of the text below. Change as little as possible while ensuring correctness."
    return _call(text, system=sys, model=model)
