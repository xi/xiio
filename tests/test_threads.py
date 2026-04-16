import time

import xiio
from tests.utils import XiioTestCase


class TestThreads(XiioTestCase):
    async def test_in_thread(self):
        with self.assert_duration(0.1):
            await xiio.gather([
                xiio.in_thread(time.sleep, 0.1),
                xiio.in_thread(time.sleep, 0.1),
                xiio.in_thread(time.sleep, 0.1),
            ])

    async def test_in_thread_exception(self):
        def raise_error():
            raise NotImplementedError

        with self.assertRaises(NotImplementedError):
            await xiio.in_thread(raise_error)

    async def test_max_workers(self):
        with self.assert_duration(0.2):
            with xiio.ThreadPool(max_workers=2) as tp:
                await xiio.gather([
                    tp.run(time.sleep, 0.1),
                    tp.run(time.sleep, 0.1),
                    tp.run(time.sleep, 0.1),
                ])
