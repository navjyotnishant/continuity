"""tests/test_lock_permission_denied.py — lock_acquire on an unwritable parent.

lib/lock.py's `except OSError: return False` branch (a missing or unwritable
`.continuity/` parent) is documented in the module's own docstring as
"nothing to retry for", but no existing lock test drives it — every existing
case is a mkdir-succeeds or FileExistsError-contention path. This proves the
distinct failure mode: a permission error returns False immediately, without
retrying until timeout.
"""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib import lock as lock_module
from lib.lock import lock_acquire


@unittest.skipIf(os.name == "nt", "chmod-based permission denial is POSIX-specific")
class TestLockAcquireOnUnwritableParent(unittest.TestCase):
    def test_permission_denied_returns_false_without_retrying(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir_path = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir_path)
            os.chmod(continuity_dir_path, 0o500)  # read+execute, no write
            try:
                with mock.patch.object(lock_module.time, "sleep") as sleep_mock:
                    result = lock_acquire(continuity_dir_path, timeout=2.0)
            finally:
                os.chmod(continuity_dir_path, 0o700)

            self.assertFalse(result)
            sleep_mock.assert_not_called()

    def test_missing_parent_returns_false_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            never_created = os.path.join(tmp, "does-not-exist", ".continuity")

            self.assertFalse(lock_acquire(never_created, timeout=1.0))


if __name__ == "__main__":
    unittest.main()
