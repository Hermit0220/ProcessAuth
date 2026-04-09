"""
ai/config.py
Loads API credentials dynamically from the .env file in the project root.
The .env file is git-ignored — keys are NEVER in source code.
Uses pure python fallback to ensure it works across all python environments.
"""
import os
from pathlib import Path

def _parse_env() -> dict:
    """Safely parses the .env file without any external dependencies."""
    env_path = Path(__file__).parent.parent / ".env"
    result = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    result[key.strip()] = val.strip()
    return result

def get_groq_key() -> str:
    if os.getenv("GROQ_API_KEY"):
        return os.getenv("GROQ_API_KEY")
    return _parse_env().get("GROQ_API_KEY", "")

def get_ninja_key() -> str:
    if os.getenv("NINJA_API_KEY"):
        return os.getenv("NINJA_API_KEY")
    return _parse_env().get("NINJA_API_KEY", "")
