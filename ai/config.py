"""
ai/config.py
Loads API credentials dynamically from the .env file in the project root.
Falls back to a manual parser if python-dotenv is not installed.
The .env file is git-ignored — keys are NEVER in source code.
"""
import os
from pathlib import Path

try:
    from dotenv import dotenv_values as _dotenv_values
    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


_ENV_FILE = Path(__file__).parent.parent / ".env"


def _parse_env_file() -> dict:
    """Zero-dependency fallback that reads key=value pairs from .env."""
    result = {}
    try:
        text = _ENV_FILE.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip().strip('"').strip("'")
                result[key] = value
    except Exception:
        pass
    return result


def _load_env() -> dict:
    if _HAS_DOTENV:
        try:
            return _dotenv_values(_ENV_FILE)
        except Exception:
            pass
    return _parse_env_file()


def get_groq_key() -> str:
    v = os.getenv("GROQ_API_KEY", "")
    if v:
        return v
    return _load_env().get("GROQ_API_KEY", "")


def get_ninja_key() -> str:
    v = os.getenv("NINJA_API_KEY", "")
    if v:
        return v
    return _load_env().get("NINJA_API_KEY", "")


def get_gemini_key() -> str:
    v = os.getenv("GEMINI_API_KEY", "")
    if v:
        return v
    return _load_env().get("GEMINI_API_KEY", "")
