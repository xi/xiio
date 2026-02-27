import contextlib
import math
import os
import selectors
import time
import typing
from collections.abc import Coroutine
from collections.abc import Generator
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE

T = typing.TypeVar('T')
Files = dict[int, int]
Gen = Generator['Condition', Files, T]
Coro = Coroutine['Condition', Files, T]


class CancelledError(BaseException):
    pass


class Condition:
    def __init__(
        self,
        *,
        files: Files = {},
        futures: set['Future[typing.Any]'] = set(),
        time: float = math.inf,
    ):
        self.files = files or {}
        self.futures = futures or set()
        self.time = time

    def __await__(self) -> Gen[Files]:
        return (yield self)

    @classmethod
    def combine(cls, conditions: list['Condition']) -> 'Condition':
        result = cls()
        for condition in conditions:
            for fileno, events in condition.files.items():
                result.files.setdefault(fileno, 0)
                result.files[fileno] |= events
            result.futures |= condition.futures
            result.time = min(result.time, condition.time)
        return result

    def fulfilled(self, files: Files) -> bool:
        return (
            self.time <= time.monotonic()
            or any(future.done for future in self.futures)
            or any(
                files.get(fileno, 0) & events == events
                for fileno, events in self.files.items()
            )
        )

    def select(self) -> Files:
        sel = selectors.DefaultSelector()
        for fileno, events in self.files.items():
            sel.register(fileno, events)
        timeout = self.time - time.monotonic()
        if any(future.done for future in self.futures):
            timeout = 0
        selected = sel.select(None if timeout == math.inf else timeout)
        return {key.fd: events for key, events in selected}


class ThrowCondition(Condition):
    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self.exc = exc


class GetTaskCondition(Condition):
    pass


async def sleep(seconds: float) -> None:
    await Condition(time=time.monotonic() + seconds)


async def read(file, size: int) -> bytes:
    fileno = file if isinstance(file, int) else file.fileno()
    await Condition(files={fileno: READ})
    return os.read(fileno, size)


async def write(file, data: bytes) -> int:
    fileno = file if isinstance(file, int) else file.fileno()
    await Condition(files={fileno: WRITE})
    return os.write(fileno, data)


class Future(typing.Generic[T]):
    def __init__(self) -> None:
        self.result: T | None = None
        self.exc: BaseException | None = None
        self.done = False

    def set_result(self, value: T) -> None:
        self.result = value
        self.done = True

    def set_exception(self, exc: BaseException) -> None:
        self.exc = exc
        self.done = True

    def __await__(self) -> Gen[T]:
        yield Condition(futures={self})
        if self.exc:
            raise self.exc
        else:
            return typing.cast(T, self.result)


class Task(typing.Generic[T]):
    def __init__(self, gen: Gen[T]):
        self.gen = gen
        self._condition: Condition | None = None
        self.result: T | None = None
        self._cancel_soon: bool = False

    @property
    def condition(self) -> Condition:
        return self._condition or Condition(time=-math.inf)

    def resume(self, state: Files | BaseException) -> None:
        if self._cancel_soon:
            self._cancel_soon = False
            self._condition = self.gen.throw(CancelledError())
        elif isinstance(state, BaseException):
            self._condition = self.gen.throw(state)
        elif not self._condition:
            self._condition = next(self.gen)
        elif self.condition.fulfilled(state):
            self._condition = self.gen.send(state)

        if isinstance(self._condition, ThrowCondition):
            exc = self._condition.exc
            self._condition = None
            raise exc
        elif isinstance(self._condition, GetTaskCondition):
            self._condition = self.gen.send(typing.cast(Files, self))

    def cancel(self) -> None:
        self._cancel_soon = True
        self._condition = None


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
        parent_task = typing.cast(Task[T], await GetTaskCondition())
        gen = parent_task.gen

        async def wrapper():
            await sleep(0)
            await self
            parent_task.gen = gen
            parent_task._condition = None
            await sleep(0)

        self.tasks.append(Task(gen))
        parent_task.gen = wrapper().__await__()
        next(parent_task.gen)
        await sleep(0)

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
async def timeout(seconds: float):
    async def _timeout() -> typing.NoReturn:
        await sleep(seconds)
        raise TimeoutError

    async with TaskGroup() as tg:
        task = tg.add_task(_timeout())
        yield
        task.cancel()


def run(coro: Coro[T]) -> T:
    task = Task(coro.__await__())
    try:
        while True:
            try:
                files = task.condition.select()
            except BaseException as e:
                task.resume(e)
            else:
                task.resume(files)
    except StopIteration as e:
        return typing.cast(T, e.value)
