"""
analysis/doc_parser.py
Parses .docx files using python-docx and tracks paragraph-level diffs.
Hashes are used for comparison — raw paragraph text is NOT stored in the DB.
"""
import time
from dataclasses import dataclass, field
from typing import Callable

from docx import Document

from utils.hashing import sha256_text
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParagraphState:
    index: int
    text_hash: str
    char_count: int
    raw_text: str = ""


@dataclass
class DiffResult:
    timestamp: float = field(default_factory=time.time)
    new_chars: int = 0
    deleted_chars: int = 0
    modified_paragraphs: int = 0
    deleted_paragraphs: int = 0
    added_paragraphs: int = 0
    large_insertion: bool = False   # > 150 chars in one snapshot diff
    suspicious: bool = False
    new_texts: list[str] = field(default_factory=list)


LARGE_INSERT_THRESHOLD = 150


def _parse_doc(doc_path: str) -> list[ParagraphState]:
    """Read a .docx and return hashed paragraph states."""
    try:
        doc = Document(doc_path)
        states: list[ParagraphState] = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text or ""
            states.append(
                ParagraphState(
                    index=i,
                    text_hash=sha256_text(text),
                    char_count=len(text),
                    raw_text=text
                )
            )
        return states
    except Exception as exc:
        logger.warning("doc_parser: could not read '%s': %s", doc_path, exc)
        return []


class DocParser:
    """
    Maintains paragraph snapshots between file-change events and
    fires `on_diff(DiffResult)` with computed diff metrics.
    """

    def __init__(self, doc_path: str, on_diff: Callable[[DiffResult], None]) -> None:
        self._doc_path = doc_path
        self._on_diff  = on_diff
        self._snapshot: list[ParagraphState] = []

    def initial_snapshot(self) -> None:
        """Capture baseline state when monitoring begins."""
        self._snapshot = _parse_doc(self._doc_path)
        logger.info(
            "Initial snapshot: %d paragraphs, %d total chars",
            len(self._snapshot),
            sum(p.char_count for p in self._snapshot),
        )

    def on_file_changed(self) -> None:
        """Called by FileWatcher after debounce. Triggers a diff computation."""
        new_snap = _parse_doc(self._doc_path)
        diff = self._compute_diff(self._snapshot, new_snap)
        self._snapshot = new_snap
        self._on_diff(diff)

    # ── diff logic ─────────────────────────────────────────────────────────────

    def _compute_diff(
        self,
        old: list[ParagraphState],
        new: list[ParagraphState],
    ) -> DiffResult:
        result = DiffResult()

        old_hashes = {p.text_hash: p for p in old}
        new_hashes = {p.text_hash: p for p in new}

        for p in new:
            if p.text_hash not in old_hashes:
                result.added_paragraphs += 1
                result.new_chars += p.char_count
                if p.char_count > LARGE_INSERT_THRESHOLD:
                    result.large_insertion = True
                if p.char_count >= 80:
                    result.new_texts.append(p.raw_text)

        for p in old:
            if p.text_hash not in new_hashes:
                result.deleted_paragraphs += 1
                result.deleted_chars += p.char_count

        # Modified = same index, different hash
        min_len = min(len(old), len(new))
        for i in range(min_len):
            if old[i].text_hash != new[i].text_hash:
                delta = new[i].char_count - old[i].char_count
                if delta > 0:
                    result.new_chars += delta
                elif delta < 0:
                    result.deleted_chars += abs(delta)
                result.modified_paragraphs += 1
                if new[i].char_count >= 80:
                    result.new_texts.append(new[i].raw_text)

        result.suspicious = result.large_insertion
        logger.debug(
            "Diff: +%d chars, %d new paras, %d modified, suspicious=%s",
            result.new_chars, result.added_paragraphs,
            result.modified_paragraphs, result.suspicious,
        )
        return result
