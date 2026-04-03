"""
utils/hashing.py
Provides SHA-256 hashing utilities for clipboard content, paragraph text,
and log integrity checks.
"""
import hashlib
from typing import Union


def sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_event_row(row: dict) -> str:
    """
    Produce a deterministic hash of a single event dict, used for
    session integrity checks in the report.
    """
    parts = "|".join(str(row.get(k, "")) for k in sorted(row.keys()))
    return sha256_text(parts)


def compute_session_integrity(rows: list[dict]) -> str:
    """
    Concatenate all row hashes and produce a master session-level
    SHA-256 fingerprint. Tampering with any single log row changes
    this value.
    """
    combined = "".join(hash_event_row(r) for r in rows)
    return sha256_text(combined)
