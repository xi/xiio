import time
from unittest import mock

import xiio
from tests.utils import XiioTestCase


async def return_later(seconds, value):
    await xiio.sleep(seconds)
    return value


async def raise_later(seconds, exc):
    await xiio.sleep(seconds)
    raise exc


def interrupt_select(self):
    timeout = self.time - time.monotonic()
    if timeout > 0:
        time.sleep(timeout / 2)
        raise KeyboardInterrupt
    return {}


class TestTaskGroup(XiioTestCase):
    async def test_add_tasks_while_running(self):
        async def set_result_later(seconds, future):
            await xiio.sleep(seconds)
            future.set_result(None)

        with self.assert_duration(0.1):
            async with xiio.TaskGroup() as tg:
                future = xiio.Future()
                tg.add_task(set_result_later(0.1, future))
                await future

    async def test_exception_in_inner_block(self):
        with self.assert_duration(0):
            with self.assertRaises(ValueError):
                async with xiio.TaskGroup() as tg:
                    tg.add_task(xiio.sleep(0.3))
                    raise ValueError

    async def test_starts_tasks_on_next_pause(self):
        stack = []

        async def foo(tg):
            stack.append(1)

        async with xiio.TaskGroup() as tg:
            tg.add_task(foo(tg))
            await xiio.sleep(0.1)
            self.assertEqual(stack, [1])

    async def test_removes_finished_tasks(self):
        async with xiio.TaskGroup() as tg:
            task = tg.add_task(xiio.sleep(0.1))
            self.assertIn(task, tg.tasks)
            await xiio.sleep(0.2)
            self.assertNotIn(task, tg.tasks)


class TestGather(XiioTestCase):
    async def test_sync_values(self):
        async def return_immediately(value):
            return value

        with self.assert_duration(0):
            result = await xiio.gather([
                return_immediately(1),
                return_immediately(2),
            ])
        self.assertEqual(result, [1, 2])

    async def test_async_values(self):
        with self.assert_duration(0.2):
            result = await xiio.gather([
                return_later(0.2, 1),
                return_later(0.1, 2),
            ])
        self.assertEqual(result, [1, 2])

    async def test_raise_on_error(self):
        with self.assertRaises(ValueError):
            with self.assert_duration(0.2):
                await xiio.gather([
                    return_later(0.1, 1),
                    raise_later(0.2, ValueError),
                ])

    async def test_cancel_others_on_error(self):
        with self.assertRaises(ValueError):
            with self.assert_duration(0.1):
                await xiio.gather([
                    return_later(0.2, 1),
                    raise_later(0.1, ValueError),
                ])

    async def test_cleanup_others_on_error(self):
        async def foo():
            try:
                await xiio.sleep(0.2)
            finally:
                await xiio.sleep(0.2)

        with self.assertRaises(ValueError):
            with self.assert_duration(0.3):
                await xiio.gather([
                    foo(),
                    raise_later(0.1, ValueError),
                ])

    async def test_swallow_exceptions_during_cancellation(self):
        async def foo():
            try:
                await xiio.sleep(0.3)
            finally:
                raise ValueError

        with self.assertRaises(TypeError):
            with self.assert_duration(0.1):
                await xiio.gather([
                    foo(),
                    raise_later(0.1, TypeError),
                ])

    async def test_cleanup_on_error_while_paused(self):
        stack = []

        async def foo():
            try:
                await xiio.sleep(0.1)
            finally:
                stack.append(1)

        with mock.patch('xiio.core.Condition.select', new=interrupt_select):
            with self.assertRaises(KeyboardInterrupt):
                await xiio.gather([foo()])
        self.assertEqual(stack, [1])


class TestTimeout(XiioTestCase):
    def test_timeout_finish(self):
        async def foo():
            async with xiio.timeout(1):
                await xiio.sleep(0.2)
                return 1

        with self.assert_duration(0.2):
            result = xiio.run(foo())
        self.assertEqual(result, 1)

    async def test_timeout_throw(self):
        with self.assertRaises(TimeoutError):
            with self.assert_duration(0.1):
                async with xiio.timeout(0.1):
                    await xiio.sleep(0.3)

    async def test_timeout_no_throw(self):
        with self.assert_duration(0.1):
            async with xiio.timeout(0.1, throw=False):
                await xiio.sleep(0.3)

    async def test_timeout_none(self):
        with self.assert_duration(0.1):
            async with xiio.timeout(None):
                await xiio.sleep(0.1)
