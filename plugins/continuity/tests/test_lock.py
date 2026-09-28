"""tests/test_lock.py — lib/lock.py's `os.mkdir()`-based store lock.

research.md R2: acquiring the lock is one atomic `os.mkdir()`, contention
retries with a brief sleep until the holder releases or `timeout` elapses,
and a lock directory older than `STALE_SECONDS` is treated as an abandoned
writer's debris and broken rather than honored forever.
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib import lock as lock_module
from lib.lock import lock_acquire, lock_path, lock_release


class TestLockAcquireNoContention(unittest.TestCase):
    def test_acquire_succeeds_immediately_when_no_contention(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(lock_acquire(tmp))
            self.assertTrue(os.path.isdir(lock_path(tmp)))


class TestLockAcquireContention(unittest.TestCase):
    def test_acquire_retries_and_succeeds_when_holder_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(lock_acquire(tmp))  # this test is the "holder"

            def release_soon():
                time.sleep(0.1)
                lock_release(tmp)

            threading.Thread(target=release_soon).start()

            waiter_result = {}

            def waiter():
                waiter_result["acquired"] = lock_acquire(tmp, timeout=2.0)

            waiter_thread = threading.Thread(target=waiter)
            waiter_thread.start()
            waiter_thread.join(timeout=3.0)

            self.assertTrue(waiter_result.get("acquired"))


class TestLockAcquireTimeout(unittest.TestCase):
    def test_acquire_times_out_and_returns_false_on_prolonged_contention(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(lock_acquire(tmp))  # never released within this test

            # Drive the deadline check without a real multi-second wait: the
            # first time.monotonic() call sets the deadline, the second (made
            # inside the loop, after the mkdir attempt) reports it already
            # elapsed.
            with mock.patch.object(
                lock_module.time, "monotonic", side_effect=[0.0, lock_module.DEFAULT_TIMEOUT]
            ), mock.patch.object(lock_module.time, "sleep") as sleep_mock:
                self.assertFalse(lock_acquire(tmp))
            sleep_mock.assert_not_called()


class TestLockStaleRemoval(unittest.TestCase):
    def test_stale_lock_older_than_ten_seconds_is_removed_and_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = lock_path(tmp)
            os.mkdir(path)
            stale_time = time.time() - (lock_module.STALE_SECONDS + 5)
            os.utime(path, (stale_time, stale_time))

            self.assertTrue(lock_acquire(tmp))
            # Reacquired means a *fresh* lock dir exists, not the stale one.
            self.assertTrue(os.path.isdir(path))
            self.assertLess(time.time() - os.path.getmtime(path), lock_module.STALE_SECONDS)


class TestLockReleasedAroundWrite(unittest.TestCase):
    def test_lock_released_after_write_memory_completes(self):
        sys.path.insert(0, REPO_ROOT)
        from lib.write_memory import write_memory

        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir_path = os.path.join(tmp, ".continuity")
            staged = os.path.join(continuity_dir_path, ".staged")
            os.makedirs(staged)
            with open(os.path.join(staged, "task-1.md"), "w", encoding="utf-8") as handle:
                handle.write("# a task\n\nbody\n")

            write_memory(tmp, "file-change")

            self.assertFalse(os.path.isdir(lock_path(continuity_dir_path)))

    def test_lock_released_after_write_memory_fails_mid_consolidate(self):
        sys.path.insert(0, REPO_ROOT)
        from lib import write_memory as write_memory_module

        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir_path = os.path.join(tmp, ".continuity")
            staged = os.path.join(continuity_dir_path, ".staged")
            os.makedirs(staged)
            with open(os.path.join(staged, "task-1.md"), "w", encoding="utf-8") as handle:
                handle.write("# a task\n\nbody\n")

            with mock.patch.object(
                write_memory_module, "_consolidate", side_effect=RuntimeError("boom")
            ):
                with self.assertRaises(RuntimeError):
                    write_memory_module.write_memory(tmp, "file-change")

            self.assertFalse(os.path.isdir(lock_path(continuity_dir_path)))


class TestLockSerializesConcurrentInvocations(unittest.TestCase):
    def test_multiple_concurrent_invocations_serialize_one_succeeds_others_wait_or_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(lock_acquire(tmp))  # simulate one hook already holding it

            results = [None, None, None]

            def contender(index, timeout):
                results[index] = lock_acquire(tmp, timeout=timeout)

            threads = [
                threading.Thread(target=contender, args=(0, 0.3)),
                threading.Thread(target=contender, args=(1, 0.3)),
                threading.Thread(target=contender, args=(2, 0.3)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2.0)

            # The holder never released: every contender must have timed out,
            # never overlapping the holder's claim on the same lock directory.
            self.assertEqual(results, [False, False, False])
            self.assertTrue(os.path.isdir(lock_path(tmp)))


if __name__ == "__main__":
    unittest.main()
