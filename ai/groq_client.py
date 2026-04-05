"""
ai/groq_client.py
Calls the Groq API (OpenAI-compatible endpoints) directly via requests.
"""
from __future__ import annotations

import textwrap
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_MODEL   = "llama-3.3-70b-versatile"
_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT = 10  # Groq is very fast, if it takes longer than 10s it's failed

def _call(prompt: str) -> str:
    """POST a single prompt to Groq. Fails fast on errors."""
    from ai.config import get_groq_key
    groq_key = get_groq_key()
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1500
    }
    
    try:
        resp = requests.post(_API_URL, headers=headers, json=payload, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Could not reach the AI service. Check your internet connection.")
    except requests.exceptions.Timeout:
        raise RuntimeError("The AI took too long to respond. Please try again.")

    if resp.status_code == 200:
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected response format: {data}") from exc

    try:
        message = resp.json().get("error", {}).get("message", resp.text)
    except Exception:
        message = resp.text

    if resp.status_code == 429:
        raise RuntimeError("Rate limit reached. Please wait a moment and try again.")
    if resp.status_code in (401, 403):
        raise RuntimeError("API key rejected. Check your .env GROQ_API_KEY.")

    raise RuntimeError(f"Groq error {resp.status_code}: {message}")


# ── Local intent heuristic (zero API cost — for UI badge only) ─────────────────

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


# ── Auto mode: single smart call ───────────────────────────────────────────────

_AUTO_PROMPT = textwrap.dedent("""\
    You are a smart AI assistant. Analyze the user's input and respond appropriately:

    - If the user wants text IMPROVED, REWRITTEN, or HUMANIZED → rewrite it naturally
      and conversationally. Preserve all original meaning. Sound like a real person wrote it.
    - If the user asks a QUESTION or wants an EXPLANATION → answer clearly and naturally,
      like a knowledgeable friend, not a textbook.
    - If the user wants a SUMMARY of long text → condense into clear key points.
    - If the user wants FACTS, DATA, or a DEFINITION → provide accurate information naturally.

    Rules:
    - Reply with ONLY the final result — no labels, no 'I will now...', no meta-commentary.
    - Use a natural, human tone. Vary sentence length. Use contractions where appropriate.
    - Never mention that you classified or detected anything.

    {context_block}User input:
    \"\"\"{text}\"\"\"

    Response:""")

def smart_respond(text: str, context: str = "") -> str:
    block = ""
    if context.strip():
        block = f"Relevant background information:\n---\n{context[:2000]}\n---\n\n"
    return _call(_AUTO_PROMPT.format(context_block=block, text=text))

# ── Manual mode functions ───────────────────────────────────────────────────

_HUMANIZE_PROMPT = textwrap.dedent("""\
    You are a professional ghostwriter. Rewrite the following text so it sounds
    natural, warm, and human. Rules:
    - Preserve every original idea and fact.
    - Vary sentence length and structure.
    - Use contractions where natural (it's, don't, I've, etc.).
    - Remove robotic phrasing.
    - Return ONLY the rewritten text — no explanation.

    Original:
    \"\"\"{text}\"\"\"

    Rewritten:""")

def humanize(text: str) -> str:
    return _call(_HUMANIZE_PROMPT.format(text=text))

_ASK_PROMPT = textwrap.dedent("""\
    Answer the following clearly and naturally — like a knowledgeable friend,
    not a textbook. Be concise but complete.

    {context_block}Question: \"\"\"{prompt}\"\"\"

    Answer:""")

def ask(prompt: str, context: str = "") -> str:
    block = f"Reference:\n---\n{context[:2500]}\n---\n\n" if context.strip() else ""
    return _call(_ASK_PROMPT.format(context_block=block, prompt=prompt))

_FACTS_PROMPT = textwrap.dedent("""\
    Provide accurate, interesting information on the following topic.
    Write naturally — no lists unless asked. Under 200 words unless more is needed.

    {context_block}Topic: \"\"\"{topic}\"\"\"

    Response:""")

def facts(topic: str, context: str = "") -> str:
    block = f"Background:\n---\n{context[:2500]}\n---\n\n" if context.strip() else ""
    return _call(_FACTS_PROMPT.format(context_block=block, topic=topic))

_SUMMARIZE_PROMPT = textwrap.dedent("""\
    Summarize the following into clear, concise key points. Use natural prose
    unless the content is list-like. Capture every important idea.

    Text:
    \"\"\"{text}\"\"\"

    Summary:""")

def summarize(text: str) -> str:
    return _call(_SUMMARIZE_PROMPT.format(text=text))
