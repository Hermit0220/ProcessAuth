"""
monitoring/file_watcher.py
Uses watchdog to detect modifications to the monitored .docx file.
A 1.5s debounce prevents duplicate parse events on rapid saves.
"""
import os
import threading
import time
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from utils.logger import get_logger

logger = get_logger(__name__)

DEBOUNCE_SECONDS = 1.5


class _DocxHandler(FileSystemEventHandler):
    def __init__(self, filepath: str, callback: Callable[[], None]) -> None:
        super().__init__()
        self._filepath = os.path.normcase(os.path.abspath(filepath))
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        if os.path.normcase(os.path.abspath(event.src_path)) != self._filepath:
            return
        self._debounce()

    def _debounce(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._callback)
            self._timer.daemon = True
            self._timer.start()


class FileWatcher:
    """
    Watches a single .docx file for modifications.
    Triggers `on_change()` at most once per DEBOUNCE_SECONDS window.
    """

    def __init__(self, doc_path: str, on_change: Callable[[], None]) -> None:
        self._doc_path = doc_path
        self._on_change = on_change
        self._observer: Observer | None = None

    def start(self) -> None:
        watch_dir = os.path.dirname(os.path.abspath(self._doc_path))
        handler = _DocxHandler(self._doc_path, self._on_change)
        self._observer = Observer()
        self._observer.schedule(handler, watch_dir, recursive=False)
        self._observer.start()
        logger.info("FileWatcher started on: %s", self._doc_path)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        logger.info("FileWatcher stopped.")
