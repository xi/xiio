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
Gen = Generator['Condition', None, T]
Coro = Coroutine['Condition', None, T]


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

    def __await__(self) -> Gen[None]:
        yield self

    def select(self) -> None:
        sel = selectors.DefaultSelector()
        for fileno, events in self.files.items():
            sel.register(fileno, events)
        timeout = self.time - time.monotonic()
        if any(future.done for future in self.futures):
            timeout = 0
        sel.select(None if timeout == math.inf else timeout)


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


def run(coro: Coro[T]) -> T:
    gen = coro.__await__()
    try:
        condition = next(gen)
        while True:
            try:
                condition.select()
            except BaseException as e:
                condition = gen.throw(e)
            else:
                condition = next(gen)
    except StopIteration as e:
        return typing.cast(T, e.value)
