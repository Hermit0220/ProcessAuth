"""
ai/ollama_client.py
<<<<<<< Updated upstream
Wrapper around the local Ollama daemon (http://127.0.0.1:11434).
Drop-in replacement for groq_client in humanizer_engine.py.
"""
from __future__ import annotations
=======

Handles text generation locally via Ollama. No cloud API needed!
Requires Ollama desktop app to be running (port 11434).
"""
>>>>>>> Stashed changes
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

<<<<<<< Updated upstream
_BASE    = "http://127.0.0.1:11434"
_TIMEOUT = 120
_DEFAULT = "llama3.2:latest"


def _call(prompt: str, system: str = "", model = None) -> str:
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
            logger.error("Ollama 404: %s", resp.text)
            return (
                f"Ollama Error: The model '{mdl}' was not found.\n"
                f"Please run 'ollama pull {mdl}' in your terminal."
            )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.ConnectionError:
        return (
            "Cannot connect to local Ollama.\n"
            "Make sure Ollama is installed and running "
            "(look for the llama icon in your system tray)."
        )
    except Exception as exc:
        logger.error("Ollama error: %s", exc)
        return f"Local AI error: {exc}"


def fetch_local_models() -> list:
    try:
        resp = requests.get(f"{_BASE}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:
        logger.warning("Could not fetch Ollama models: %s", exc)
        return []


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
=======
# Default to local daemon
OLLAMA_URL = "http://127.0.0.1:11434"

# Default fallback model in case fetching fails or UI hasn't specified one
_DEFAULT_MODEL = "llama3.2:latest"

def fetch_local_models() -> list[str]:
    """Queries the local Ollama daemon for downloaded models."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("name") for m in data.get("models", [])]
            return sorted(models)
    except Exception as e:
        logger.warning(f"Could not fetch Ollama models: {e}")
    return []

def _call(prompt: str, system: str = "", model: str = None) -> str:
    """Send a prompt to the local Ollama API."""
    target_model = model if model else _DEFAULT_MODEL
    
    url = f"{OLLAMA_URL}/api/chat"
    payload = {
        "model": target_model,
        "messages": [],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
        }
    }
    
    if system:
        payload["messages"].append({"role": "system", "content": system})
    payload["messages"].append({"role": "user", "content": prompt})

    try:
        resp = requests.post(url, json=payload, timeout=90)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()
        else:
            logger.error(f"Ollama API Error {resp.status_code}: {resp.text}")
            if resp.status_code == 404:
                return f"Ollama Error: The model '{target_model}' was not found. Please run 'ollama pull {target_model}' in your terminal."
            return f"Local Engine Error: {resp.text}"
    except requests.exceptions.ConnectionError:
        return ("Ollama not found. Please ensure Ollama is installed "
                "from ollama.com and is currently running on your computer.")
    except Exception as e:
        logger.exception("Ollama request failed.")
        return f"Engine Error: {e}"

# ─────────────────────────────────────────────────────────────────────────────
# Feature Prompts Modeled after our other clients
# ─────────────────────────────────────────────────────────────────────────────

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
>>>>>>> Stashed changes
        return "Ask"
    if len(text) > 200 and "?" not in text:
        return "HumanRewrite"
    return "Ask"


<<<<<<< Updated upstream
def smart_respond(text: str, context: str = "", model=None) -> str:
    sys = (
        "You are an expert AI humanizer. Remove all AI-like patterns. "
        "Output ONLY the final content. Never apologize or refuse."
    )
    prompt = f"[CONTEXT]\n{context}\n\n[INPUT]\n{text}" if context else text
    return _call(prompt, system=sys, model=model)


def humanize(text: str, model=None) -> str:
    sys = (
        "You are an expert human copywriter. Rewrite to bypass AI detection.\n"
        "Rules:\n"
        "1. Mix short and long sentences aggressively.\n"
        "2. Use unexpected word choices.\n"
        "3. Never use: 'In conclusion', 'Furthermore', 'Moreover', 'It is important'.\n"
        "4. Add casual anchors: 'Honestly,', 'Well,', 'To be fair,'\n"
        "5. Vary paragraph lengths. One-line paragraphs are powerful.\n"
        "Output ONLY the rewritten text. No intro or explanation."
    )
    return _call(text, system=sys, model=model)


def summarize(text: str, model=None) -> str:
    sys = (
        "Summarize the text concisely in plain, natural language. "
        "No bullet points unless asked. 2-4 short paragraphs max. Output ONLY the summary."
    )
    return _call(text, system=sys, model=model)


def ask(prompt: str, context: str = "", model=None) -> str:
    sys = "Answer clearly and naturally like a knowledgeable friend. Be concise but complete."
    if context.strip():
        sys += f"\nReference:\n---\n{context[:2500]}\n---"
    return _call(prompt, system=sys, model=model)


def facts(topic: str, context: str = "", model=None) -> str:
    sys = "Provide accurate, interesting information. Write naturally. Under 200 words."
    if context.strip():
        sys += f"\nBackground:\n---\n{context[:2500]}\n---"
    return _call(topic, system=sys, model=model)


def academic(text: str, model=None) -> str:
    return _call(text, system="Rewrite in formal academic prose. Avoid AI cliches.", model=model)


def creative(text: str, model=None) -> str:
    return _call(text, system="Rewrite to sound creative, vibrant, and engaging.", model=model)


def simplify(text: str, model=None) -> str:
    return _call(text, system="Rewrite so an 8th grader understands it effortlessly.", model=model)


def grammar(text: str, model=None) -> str:
    return _call(text, system="Fix grammar, spelling, and flow. Change as little as possible.", model=model)
=======
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

def academic(text: str, model: str = None) -> str:
    sys = "Rewrite the following text in formal academic prose. Use sophisticated vocabulary but avoid AI-cliches."
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

def summarize(text: str, model: str = None) -> str:
    sys = "Provide a comprehensive yet concise summary of the text below. Extract the core arguments."
    return _call(text, system=sys, model=model)

# ── Quicks ──

def quick_fact(model: str = None) -> str:
    return _call("Tell me a fascinating, somewhat obscure random fact. Be concise.", model=model)

def quick_quote(model: str = None) -> str:
    return _call("Give me a powerful, inspiring quote followed by its author.", model=model)
>>>>>>> Stashed changes
