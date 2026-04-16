import contextlib
import math
import typing
from collections.abc import AsyncGenerator

from .core import CancelledError
from .core import Condition
from .core import Coro
from .core import Gen
from .core import SwitchGenCondition
from .core import Task
from .core import ThrowCondition
from .core import sleep

T = typing.TypeVar('T')


class TaskGroup(typing.Generic[T]):
    def __init__(self) -> None:
        self.tasks: list[Task[T]] = []
        self.exc: BaseException | None = None

    def add_task(self, coro: Coro[T]) -> Task[T]:
        task = Task(coro.__await__())
        self.tasks.append(task)
        return task

    def cancel(self, exc: BaseException) -> None:
        if not self.exc:
            self.exc = exc
            for task in self.tasks:
                task.cancel()

    def __await__(self) -> Gen[None]:
        while self.tasks:
            try:
                state = yield Condition.combine(
                    [task.condition for task in self.tasks]
                )
            except BaseException as e:
                state = e

            for task in self.tasks[:]:
                try:
                    task.resume(state)
                except StopIteration as e:
                    self.tasks.remove(task)
                    task.result = e.value
                except CancelledError:
                    self.tasks.remove(task)
                except BaseException as e:
                    self.tasks.remove(task)
                    self.cancel(e)

    async def __aenter__(self) -> 'TaskGroup[T]':
        async def wrapper():
            await self
            await SwitchGenCondition(parent_gen)
            await Condition(time=-math.inf)

        wrapper_gen = typing.cast(Gen, wrapper().__await__())
        parent_gen = typing.cast(Gen, await SwitchGenCondition(wrapper_gen))
        self.tasks.append(Task(parent_gen))
        await next(wrapper_gen)

        return self

    async def __aexit__(self, exc_type, exc: BaseException | None, traceback) -> None:
        await ThrowCondition(exc or StopIteration())
        if self.exc:
            raise self.exc


async def gather(coros: list[Coro[T]]) -> list[T]:
    async with TaskGroup() as tg:
        tasks = [tg.add_task(coro) for coro in coros]
    return [typing.cast(T, task.result) for task in tasks]


@contextlib.asynccontextmanager
async def timeout(
    seconds: float | None, *, throw: bool = True
) -> AsyncGenerator[None, None]:
    if seconds is None:
        yield
    else:
        async def _timeout() -> typing.NoReturn:
            await sleep(seconds)
            raise TimeoutError

        try:
            async with TaskGroup() as tg:
                task = tg.add_task(_timeout())
                yield
                task.cancel()
        except TimeoutError:
            if throw:
                raise
