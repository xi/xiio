import os
import time
from unittest import mock

import xiio
from tests.utils import XiioTestCase
from xiio.core import READ
from xiio.core import WRITE
from xiio.core import Condition


def interrupt_select(self):
    timeout = self.time - time.monotonic()
    if timeout > 0:
        time.sleep(timeout / 2)
        raise KeyboardInterrupt
    return {}


class TestConditionCombine(XiioTestCase):
    def test_time(self):
        result = Condition.combine([
            Condition(),
            Condition(time=1),
            Condition(time=3),
            Condition(time=-2),
        ])
        self.assertEqual(result.time, -2)

    def test_futures(self):
        f1 = xiio.Future()
        f2 = xiio.Future()
        _f3 = xiio.Future()

        result = Condition.combine([
            Condition(),
            Condition(futures={f1}),
            Condition(futures={f1, f2}),
        ])

        self.assertEqual(result.futures, {f1, f2})

    def test_files(self):
        result = Condition.combine([
            Condition(),
            Condition(files={1: READ, 2: READ}),
            Condition(files={1: WRITE}),
        ])

        self.assertEqual(result.files, {
            1: READ|WRITE,
            2: READ,
        })


class TestConditionFulfilled(XiioTestCase):
    def test_files(self):
        condition = Condition(files={1: READ})
        self.assertTrue(condition.fulfilled({1: READ, 2: READ}))

    def test_files_wrong_mode(self):
        condition = Condition(files={1: READ})
        self.assertFalse(condition.fulfilled({1: WRITE, 2: READ}))

    def test_future_not_done(self):
        future = xiio.Future()
        condition = Condition(futures={future})
        self.assertFalse(condition.fulfilled({}))

    def test_future_result(self):
        future = xiio.Future()
        future.set_result(1)
        condition = Condition(futures={future})
        self.assertTrue(condition.fulfilled({}))

    def test_future_exception(self):
        future = xiio.Future()
        future.set_exception(ValueError)
        condition = Condition(futures={future})
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

        with mock.patch('xiio.core.Condition.select', new=interrupt_select):
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
                    xiio.writeall(w, b'Hello World'),
                ])
            finally:
                os.close(w)
                os.close(r)

        with self.assert_duration(0):
            result = xiio.run(foo())
        self.assertEqual(result, [b'Hello World', None])
