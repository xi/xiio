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
    pass
