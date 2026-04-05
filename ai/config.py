"""
ai/config.py
Loads API credentials dynamically from the .env file in the project root.
The .env file is git-ignored — keys are NEVER in source code.
"""
import os
from pathlib import Path

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

def get_groq_key() -> str:
    if os.getenv("GROQ_API_KEY"):
        return os.getenv("GROQ_API_KEY")
    if dotenv_values:
        env_dict = dotenv_values(Path(__file__).parent.parent / ".env")
        return env_dict.get("GROQ_API_KEY", "")
    return ""

def get_ninja_key() -> str:
    if os.getenv("NINJA_API_KEY"):
        return os.getenv("NINJA_API_KEY")
    if dotenv_values:
        env_dict = dotenv_values(Path(__file__).parent.parent / ".env")
        return env_dict.get("NINJA_API_KEY", "")
    return ""
