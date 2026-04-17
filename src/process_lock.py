from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .project_config import REPO_ROOT
from .project_constants import PROCESS_LOCK_FILENAME


logger = logging.getLogger(__name__)
LOCK_FILE_PATH = REPO_ROOT / PROCESS_LOCK_FILENAME


def _lock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class SingleInstanceLock:
    def __init__(self, lock_file_path: Path = LOCK_FILE_PATH):
        self.lock_file_path = lock_file_path
        self._handle = None

    def acquire(self) -> bool:
        self.lock_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.lock_file_path, "a+", encoding="utf-8")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(" ")
            self._handle.flush()

        try:
            _lock_handle(self._handle)
        except OSError:
            self._handle.close()
            self._handle = None
            return False

        self._handle.seek(0)
        self._handle.truncate()
        self._handle.write(json.dumps({"pid": os.getpid()}))
        self._handle.flush()
        return True

    def release(self) -> None:
        if self._handle is None:
            return

        try:
            _unlock_handle(self._handle)
        finally:
            self._handle.close()
            self._handle = None
