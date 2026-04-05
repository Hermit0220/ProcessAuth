"""
ai/config.py
Loads API credentials from the .env file in the project root.
The .env file is git-ignored — keys are NEVER in source code.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on system env vars

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
NINJA_API_KEY:  str = os.getenv("NINJA_API_KEY",  "")
