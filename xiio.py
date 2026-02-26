import math
import os
import selectors
import time
from selectors import EVENT_READ as READ
from selectors import EVENT_WRITE as WRITE


class Condition:
    def __init__(self, *, files={}, time=math.inf):
        self.files = files or {}
        self.time = time

    def __await__(self):
        yield self

    def select(self):
        sel = selectors.DefaultSelector()
        for fileno, events in self.files.items():
            sel.register(fileno, events)
        timeout = self.time - time.monotonic()
        sel.select(None if timeout == math.inf else timeout)


async def sleep(seconds):
    await Condition(time=time.monotonic() + seconds)


async def read(file, size):
    fileno = file if isinstance(file, int) else file.fileno()
    await Condition(files={fileno: READ})
    return os.read(fileno, size)


async def write(file, data):
    fileno = file if isinstance(file, int) else file.fileno()
    await Condition(files={fileno: WRITE})
    return os.write(fileno, data)


def run(coro):
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
        return e.value
