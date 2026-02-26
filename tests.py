import contextlib
import time
import unittest
from unittest import mock

import xiio


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
        async def foo():
            await xiio.sleep(0.1)
            return 'Hello World'

        with self.assert_duration(0.1):
            result = xiio.run(foo())
        self.assertEqual(result, 'Hello World')

    def test_runs_cleanup_on_error_while_paused(self):
        stack = []

        async def foo():
            try:
                await xiio.sleep(0.1)
            finally:
                stack.append(1)

        with mock.patch('xiio.Condition.select', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                xiio.run(foo())
        self.assertEqual(stack, [1])

    def test_waits_for_cleanup(self):
        async def foo():
            try:
                raise ValueError
            finally:
                await xiio.sleep(0.1)

        with self.assertRaises(ValueError):
            with self.assert_duration(0.1):
                xiio.run(foo())
