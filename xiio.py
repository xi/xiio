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

    def cancel(self) -> None:
        self._cancel_soon = True
        self._condition = None


async def gather(coros: list[Coro[T]]) -> list[T]:
    tasks = [Task(coro.__await__()) for coro in coros]
    remaining = tasks[:]
    exc = None

    while remaining:
        try:
            state = await Condition.combine(
                [task.condition for task in remaining]
            )
        except BaseException as e:
            state = e

        for task in remaining[:]:
            try:
                task.resume(state)
            except StopIteration as e:
                remaining.remove(task)
                task.result = e.value
            except BaseException as e:
                remaining.remove(task)
                if not exc:
                    exc = e
                    for task in remaining:
                        task.cancel()

    if exc:
        raise exc

    return [typing.cast(T, task.result) for task in tasks]


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
