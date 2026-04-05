"""
ai/gemini_client.py
Calls the Gemini REST API directly via requests — no SDK, no namespace conflicts.
Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

Free-tier note: 15 RPM limit. On 429, the caller receives a friendly message.
"""
from __future__ import annotations

import textwrap
import time
import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_MODEL   = "gemini-2.0-flash"
_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_MODEL}:generateContent"
)
_TIMEOUT = 30  # seconds


def _call(prompt: str) -> str:
    """POST a prompt to the Gemini REST API and return the text response.
    Retries once after 65 s on a 429 to respect the free-tier RPM window."""
    from ai.config import GEMINI_API_KEY
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
    }

    for attempt in range(2):
        try:
            resp = requests.post(
                _API_URL,
                params={"key": GEMINI_API_KEY},
                json=payload,
                timeout=_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                "Could not reach the AI service. Check your internet connection."
            ) from exc

        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError) as exc:
                raise RuntimeError(f"Unexpected response format: {data}") from exc

        if resp.status_code == 429 and attempt == 0:
            # Free-tier: 15 RPM — wait one minute then retry once
            logger.warning("Gemini 429 — waiting 65 s before retry")
            time.sleep(65)
            continue

        # All other errors
        try:
            message = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            message = resp.text
        raise RuntimeError(f"{resp.status_code} {message}")

    raise RuntimeError("Rate limit reached. Please wait a moment and try again.")


# ── Intent Classification ──────────────────────────────────────────────────────

_INTENT_PROMPT = textwrap.dedent("""\
    You are an intent classifier. Given the user input below, decide which
    processing mode fits best. Reply with EXACTLY one of these words — nothing else:
      HumanRewrite  — user wants text improved, rewritten, or humanized
      Ask           — user is asking a question or wants an explanation
      Facts         — user wants real-world data, weather, or a specific fact
      Summarize     — user wants a long text condensed into key points

    User input:
    \"\"\"{text}\"\"\"

    Mode:""")


def classify_intent(text: str) -> str:
    """Returns one of: HumanRewrite | Ask | Facts | Summarize"""
    try:
        raw = _call(_INTENT_PROMPT.format(text=text[:800]))
        for token in ("HumanRewrite", "Ask", "Facts", "Summarize"):
            if token.lower() in raw.lower():
                logger.info("Intent classified as: %s", token)
                return token
        logger.warning("Unrecognised intent '%s', defaulting to Ask", raw)
        return "Ask"
    except Exception as exc:
        logger.error("Intent classification failed: %s", exc)
        return "Ask"


# ── HumanRewrite ──────────────────────────────────────────────────────────────

_HUMANIZE_PROMPT = textwrap.dedent("""\
    You are a professional editor and ghostwriter. Rewrite the following text so
    it sounds natural, warm, and human — as if a thoughtful person wrote it.
    Rules:
    - Preserve every idea and fact from the original.
    - Vary sentence length and structure; avoid repetitive patterns.
    - Use contractions where they sound natural (it's, don't, I've, etc.).
    - Remove robotic or overly formal phrasing.
    - Never add content that wasn't implied by the original.
    - Return ONLY the rewritten text — no explanations, no commentary.

    Original text:
    \"\"\"{text}\"\"\"

    Rewritten version:""")


def humanize(text: str) -> str:
    return _call(_HUMANIZE_PROMPT.format(text=text))


# ── Ask ────────────────────────────────────────────────────────────────────────

_ASK_PROMPT = textwrap.dedent("""\
    You are a knowledgeable, conversational assistant. Answer the following
    clearly and naturally — like a smart friend explaining something, not a
    textbook. Be concise but complete. Use plain language.

    Question: \"\"\"{prompt}\"\"\"

    Answer:""")

_ASK_WITH_CONTEXT_PROMPT = textwrap.dedent("""\
    You are a knowledgeable assistant. Use the reference material below to help
    answer the question accurately. Write in a natural, conversational tone.
    Do NOT mention that you used any reference material.

    Reference:
    ---
    {context}
    ---

    Question: \"\"\"{prompt}\"\"\"

    Answer:""")


def ask(prompt: str, context: str = "") -> str:
    if context.strip():
        return _call(_ASK_WITH_CONTEXT_PROMPT.format(
            context=context[:3000], prompt=prompt))
    return _call(_ASK_PROMPT.format(prompt=prompt))


# ── Facts ─────────────────────────────────────────────────────────────────────

_FACTS_PROMPT = textwrap.dedent("""\
    You are a factual assistant. Answer with accurate, interesting information.
    Write naturally — no bullet lists unless the user asks. Under 200 words unless more is needed.

    {context_block}Topic / Question: \"\"\"{topic}\"\"\"

    Response:""")


def facts(topic: str, context: str = "") -> str:
    block = ""
    if context.strip():
        block = f"Background from trusted sources:\n---\n{context[:2500]}\n---\n\n"
    return _call(_FACTS_PROMPT.format(context_block=block, topic=topic))


# ── Summarize ─────────────────────────────────────────────────────────────────

_SUMMARIZE_PROMPT = textwrap.dedent("""\
    Summarize the following text into clear, concise key points. Use natural
    prose unless the content is clearly list-like. Capture every important idea.
    Do not add opinions or new information.

    Text: \"\"\"{text}\"\"\"

    Summary:""")


def summarize(text: str) -> str:
    return _call(_SUMMARIZE_PROMPT.format(text=text))
