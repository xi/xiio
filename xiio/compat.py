import asyncio
import os
import typing

from .core import READ
from .core import WRITE
from .core import Coro
from .core import Files
from .core import Task

T = typing.TypeVar('T')


async def asyncio_select(files: Files, timeout: float | None) -> Files:
    if timeout is not None and timeout <= 0:
        return {}

    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def callback(fd, events):
        if not future.done():
            future.set_result({fd: events})

    # duplicate file descriptors so we don't remove existing callbacks
    dups = {fd: os.dup(fd) for fd in files}

    for fd, events in files.items():
        if events & READ:
            loop.add_reader(dups[fd], callback, fd, READ)
        if events & WRITE:
            loop.add_writer(dups[fd], callback, fd, WRITE)

    try:
        async with asyncio.timeout(timeout):
            return await future
    except TimeoutError:
        return {}
    finally:
        for dup in dups.values():
            loop.remove_reader(dup)
            loop.remove_writer(dup)
            os.close(dup)


async def on_asyncio(coro: Coro[T]) -> T:
    task = Task(coro.__await__())
    try:
        while True:
            try:
                files = await asyncio_select(
                    task.condition.files, task.condition.timeout
                )
            except BaseException as e:
                task.resume(e)
            else:
                task.resume(files)
    except StopIteration as e:
        return typing.cast(T, e.value)
