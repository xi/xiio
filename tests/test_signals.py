import os
import signal

import xiio
from tests.utils import XiioTestCase


class TestSubscribeSignals(XiioTestCase):
    async def test_subscribe_signals(self):
        result = []

        async def send_signals():
            await xiio.sleep(0.1)
            os.kill(os.getpid(), signal.Signals.SIGUSR1)

        async with xiio.TaskGroup() as tg:
            async with xiio.subscribe_signals(signal.Signals.SIGUSR1) as signal_fd:
                tg.add_task(send_signals())
                with self.assert_duration(0.1):
                    result = await xiio.read(signal_fd, 1)
                self.assertEqual(result[0], signal.Signals.SIGUSR1)
