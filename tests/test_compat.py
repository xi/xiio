import asyncio
import contextlib
import os
import time
import unittest

import xiio


class TestOnAsyncIO(unittest.IsolatedAsyncioTestCase):
    @contextlib.contextmanager
    def assert_duration(self, expected, *, places=1):
        start = time.monotonic()
        try:
            yield
        finally:
            actual = time.monotonic() - start
            self.assertAlmostEqual(actual, expected, places=places)

    async def test_sleep(self):
        with self.assert_duration(0.1):
            await xiio.on_asyncio(xiio.sleep(0.1))

    async def test_sleep_both(self):
        with self.assert_duration(0.1):
            await asyncio.gather(
                asyncio.sleep(0.1),
                xiio.on_asyncio(xiio.sleep(0.1)),
            )

    async def test_cancel(self):
        with self.assert_duration(0.1):
            with self.assertRaises(TimeoutError):
                async with asyncio.timeout(0.1):
                    await xiio.on_asyncio(xiio.sleep(0.5))

    async def test_read(self):
        loop = asyncio.get_running_loop()
        r, w = os.pipe()
        try:
            def on_write():
                os.write(w, b'foo')
                loop.remove_writer(w)

            loop.add_writer(w, on_write)
            result = await xiio.on_asyncio(xiio.read(r, 10))
            self.assertEqual(result, b'foo')
        finally:
            os.close(r)
            os.close(w)

    async def test_write(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        r, w = os.pipe()
        try:
            def on_read():
                future.set_result(os.read(r, 10))
                loop.remove_reader(r)

            loop.add_reader(r, on_read)
            await xiio.on_asyncio(xiio.write(w, b'foo'))
            result = await future
            self.assertEqual(result, b'foo')
        finally:
            os.close(r)
            os.close(w)
