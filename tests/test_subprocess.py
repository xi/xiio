import subprocess

import xiio
from tests.utils import XiioTestCase


class TestRunProcess(XiioTestCase):
    async def test_run_process(self):
        cmd = ['sh', '-c', 'sleep 0.1 && echo "Hello World"']

        with self.assert_duration(0.1):
            result = await xiio.run_process(cmd, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'Hello World\n')

    async def test_check(self):
        await xiio.run_process(['true'], check=True)
        with self.assertRaises(subprocess.CalledProcessError):
            await xiio.run_process(['false'], check=True)

    async def test_cancel(self):
        with self.assert_duration(0.1):
            with self.assertRaises(TimeoutError):
                async with xiio.timeout(0.1):
                    await xiio.run_process(['sleep', '0.5'])
