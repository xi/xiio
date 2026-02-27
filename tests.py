import contextlib
import time
import unittest
from unittest import mock


class XiioTestCase(unittest.TestCase):
    @contextlib.contextmanager
    def assert_duration(self, expected, *, places=2):
        start = time.monotonic()
        try:
            yield
        finally:
            actual = time.monotonic() - start
            self.assertAlmostEqual(actual, expected, places=places)


class TestRun(XiioTestCase):
    def test_sleep(self):
        def foo():
            time.sleep(0.1)
            return 'Hello World'

        with self.assert_duration(0.1):
            result = foo()
        self.assertEqual(result, 'Hello World')

    def test_runs_cleanup_on_error_while_paused(self):
        stack = []

        def foo():
            try:
                time.sleep(0.1)
            finally:
                stack.append(1)

        with mock.patch('time.sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                foo()
        self.assertEqual(stack, [1])

    def test_waits_for_cleanup(self):
        def foo():
            try:
                raise ValueError
            finally:
                time.sleep(0.1)

        with self.assertRaises(ValueError):
            with self.assert_duration(0.1):
                foo()
