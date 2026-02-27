import contextlib
import functools
import inspect
import os
import time
import unittest
from unittest import mock

import xiio


async def return_later(seconds, value):
    await xiio.sleep(seconds)
    return value


async def raise_later(seconds, exc):
    await xiio.sleep(seconds)
    raise exc


class InterruptCondition(xiio.Condition):
    def select(self):
        timeout = self.time - time.monotonic()
        if timeout > 0:
            time.sleep(timeout / 2)
            raise KeyboardInterrupt
        return {}


class XiioTestCase(unittest.TestCase):
    def _callTestMethod(self, method):  # noqa
        if not inspect.iscoroutinefunction(method):
            return super()._callTestMethod(method)

        @functools.wraps(method)
        def wrapper(*args, **kwargs):
            xiio.run(method(*args, **kwargs))
        return super()._callTestMethod(wrapper)

    @contextlib.contextmanager
    def assert_duration(self, expected, *, places=2):
        start = time.monotonic()
        try:
            yield
        finally:
            actual = time.monotonic() - start
            self.assertAlmostEqual(actual, expected, places=places)


class TestConditionCombine(XiioTestCase):
    def test_time(self):
        result = xiio.Condition.combine([
            xiio.Condition(),
            xiio.Condition(time=1),
            xiio.Condition(time=3),
            xiio.Condition(time=-2),
        ])
        self.assertEqual(result.time, -2)

    def test_futures(self):
        f1 = xiio.Future()
        f2 = xiio.Future()
        _f3 = xiio.Future()

        result = xiio.Condition.combine([
            xiio.Condition(),
            xiio.Condition(futures={f1}),
            xiio.Condition(futures={f1, f2}),
        ])

        self.assertEqual(result.futures, {f1, f2})

    def test_files(self):
        result = xiio.Condition.combine([
            xiio.Condition(),
            xiio.Condition(files={1: xiio.READ, 2: xiio.READ}),
            xiio.Condition(files={1: xiio.WRITE}),
        ])

        self.assertEqual(result.files, {
            1: xiio.READ|xiio.WRITE,
            2: xiio.READ,
        })


class TestConditionFulfilled(XiioTestCase):
    def test_files(self):
        condition = xiio.Condition(files={1: xiio.READ})
        self.assertTrue(condition.fulfilled({1: xiio.READ, 2: xiio.READ}))

    def test_files_wrong_mode(self):
        condition = xiio.Condition(files={1: xiio.READ})
        self.assertFalse(condition.fulfilled({1: xiio.WRITE, 2: xiio.READ}))

    def test_future_not_done(self):
        future = xiio.Future()
        condition = xiio.Condition(futures={future})
        self.assertFalse(condition.fulfilled({}))

    def test_future_result(self):
        future = xiio.Future()
        future.set_result(1)
        condition = xiio.Condition(futures={future})
        self.assertTrue(condition.fulfilled({}))

    def test_future_exception(self):
        future = xiio.Future()
        future.set_exception(ValueError)
        condition = xiio.Condition(futures={future})
        self.assertTrue(condition.fulfilled({}))


class TestFuture(XiioTestCase):
    async def test_set_result(self):
        future = xiio.Future()
        future.set_result('test')
        result = await future
        self.assertEqual(result, 'test')

    async def test_set_exception(self):
        future = xiio.Future()
        future.set_exception(TypeError)
        with self.assertRaises(TypeError):
            await future


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

        with mock.patch('xiio.Condition', wraps=InterruptCondition):
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

    async def test_timeout_raise(self):
        with self.assertRaises(TimeoutError):
            with self.assert_duration(0.1):
                async with xiio.timeout(0.1):
                    await xiio.sleep(0.3)
                    return 1


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

        with mock.patch('xiio.Condition', wraps=InterruptCondition):
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

    def test_pipe(self):
        async def foo():
            r, w = os.pipe()
            try:
                return await xiio.gather([
                    xiio.read(r, 32),
                    xiio.write(w, b'Hello World'),
                ])
            finally:
                os.close(w)
                os.close(r)

        with self.assert_duration(0):
            result = xiio.run(foo())
        self.assertEqual(result, [b'Hello World', 11])
