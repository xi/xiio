import contextlib
import functools
import inspect
import time
import unittest

import xiio


class XiioTestCase(unittest.TestCase):
    def _callTestMethod(self, method):  # noqa
        if inspect.iscoroutinefunction(method):
            @functools.wraps(method)
            def wrapper(*args, **kwargs):
                xiio.run(method(*args, **kwargs))
        else:
            wrapper = method

        return super()._callTestMethod(wrapper)  # ty: ignore[unresolved-attribute]

    @contextlib.contextmanager
    def assert_duration(self, expected, *, places=2):
        start = time.monotonic()
        try:
            yield
        finally:
            actual = time.monotonic() - start
            self.assertAlmostEqual(actual, expected, places=places)
