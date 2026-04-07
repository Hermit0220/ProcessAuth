"""
ai/ninja_client.py
Wrapper around the API Ninjas REST endpoints (free tier).

Free-tier limitations applied:
  - quotes: no 'limit' or 'category' params (premium only)
  - facts:  'limit' param works on free tier

Endpoints used:
  /v1/facts      → random interesting fact
  /v1/quotes     → inspirational quote
  /v1/weather    → current weather for a city
  /v1/dictionary → word definition
"""
from __future__ import annotations

import requests
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE    = "https://api.api-ninjas.com/v1"
_TIMEOUT = 10


def _headers() -> dict:
    from ai.config import get_ninja_key
    ninja_key = get_ninja_key()
    if not ninja_key:
        raise RuntimeError("NINJA_API_KEY is missing. Add it to your .env file.")
    return {"X-Api-Key": ninja_key}


def _get(endpoint: str, params: dict | None = None) -> list | dict:
    url  = f"{_BASE}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ── Public API ─────────────────────────────────────────────────────────────────

def get_fact() -> str:
    """Returns a random interesting fact as a plain string."""
    try:
        data = _get("facts", {"limit": 1})
        if isinstance(data, list) and data:
            return data[0].get("fact", "No fact available.")
        return "Couldn't retrieve a fact right now."
    except Exception as exc:
        logger.error("Ninja facts error: %s", exc)
        return f"Could not load fact: {exc}"


def get_quote() -> dict:
    """Returns dict with 'quote' and 'author' keys.
    Note: limit/category params are premium-only — called with no params."""
    try:
        data = _get("quotes")          # free tier: returns 1 quote by default
        if isinstance(data, list) and data:
            return {
                "quote":  data[0].get("quote", ""),
                "author": data[0].get("author", "Unknown"),
            }
        return {"quote": "No quote available.", "author": ""}
    except Exception as exc:
        logger.error("Ninja quotes error: %s", exc)
        return {"quote": f"Could not load quote: {exc}", "author": ""}


def get_weather(city: str) -> dict:
    """Returns weather dict with temperature, humidity, wind, etc."""
    try:
        data = _get("weather", {"city": city})
        if isinstance(data, dict) and "temp" in data:
            return {
                "city":       city.title(),
                "temp":       round(data.get("temp", 0), 1),
                "feels_like": round(data.get("feels_like", 0), 1),
                "humidity":   data.get("humidity", 0),
                "wind_speed": round(data.get("wind_speed", 0), 1),
                "min_temp":   round(data.get("min_temp", 0), 1),
                "max_temp":   round(data.get("max_temp", 0), 1),
                "cloud_pct":  data.get("cloud_pct", 0),
            }
        return {"error": f"No weather data for '{city}'"}
    except Exception as exc:
        logger.error("Ninja weather error for '%s': %s", city, exc)
        return {"error": str(exc)}


def get_word_definition(word: str) -> list[dict]:
    """Returns list of definition dicts with keys: definition, part_of_speech, example."""
    try:
        data = _get("dictionary", {"word": word.strip()})
        if isinstance(data, dict):
            return [{
                "definition":    data.get("definition", "No definition found."),
                "part_of_speech": data.get("part_of_speech", ""),
                "example":       data.get("example", ""),
            }]
        if isinstance(data, list) and data:
            return data
        return [{"definition": "No definition found.", "part_of_speech": "", "example": ""}]
    except Exception as exc:
        logger.error("Ninja dictionary error for '%s': %s", word, exc)
        return [{"definition": f"Error: {exc}", "part_of_speech": "", "example": ""}]


def format_weather(w: dict) -> str:
    """Converts weather dict to a readable string."""
    if "error" in w:
        return f"⚠  Could not get weather: {w['error']}"
    return (
        f"🌤  Weather in {w.get('city', '?')}\n\n"
        f"Temperature  :  {w.get('temp', '?')}°C  "
        f"(feels like {w.get('feels_like', '?')}°C)\n"
        f"Range        :  {w.get('min_temp', '?')}°C – {w.get('max_temp', '?')}°C\n"
        f"Humidity     :  {w.get('humidity', '?')}%\n"
        f"Wind Speed   :  {w.get('wind_speed', '?')} m/s\n"
        f"Cloud Cover  :  {w.get('cloud_pct', '?')}%"
    )


def humanize(text: str) -> str:
    """Paraphrase / humanize text using the API Ninjas paraphrase endpoint."""
    try:
        url  = f"{_BASE}/paraphrase"
        resp = requests.post(
            url,
            headers=_headers(),
            json={"text": text},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        # API Ninjas returns {"result": "..."} or {"paraphrase": "..."}
        result = data.get("result") or data.get("paraphrase") or data.get("text", "")
        if result:
            return result.strip()
        return f"⚠  Ninja returned an unexpected response: {data}"
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        logger.error("Ninja paraphrase HTTP %s: %s", status, exc)
        if status == 404:
            return (
                "⚠  API Ninjas paraphrase endpoint is not available on your plan.\n"
                "Switch to a local model (llama3.2 / gemma3) in the Model dropdown."
            )
        return f"⚠  Ninja paraphrase error ({status}): {exc}"
    except Exception as exc:
        logger.error("Ninja humanize error: %s", exc)
        return f"⚠  Could not reach API Ninjas: {exc}"
