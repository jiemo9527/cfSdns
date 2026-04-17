import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.process_lock import SingleInstanceLock


class ProcessLockTests(unittest.TestCase):
    def test_single_instance_lock_blocks_second_acquire_until_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / ".cfsdns.lock"
            first_lock = SingleInstanceLock(lock_path)
            second_lock = SingleInstanceLock(lock_path)

            self.assertTrue(first_lock.acquire())
            self.assertFalse(second_lock.acquire())

            first_lock.release()
            self.assertTrue(second_lock.acquire())
            second_lock.release()
